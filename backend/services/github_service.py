"""
services/github_service.py
---------------------------
Top-level orchestrator for the GitHub push webhook workflow.

Responsibilities:
- Validate the GitHub webhook HMAC-SHA256 signature
- Coordinate the full end-to-end pipeline:
    1. Extract repository info from the payload
    2. Sync the repository (clone or pull) via GitService
    3. Parse commit data via ParserService
    4. Create and persist a workflow via WorkflowService
- Return a structured result to the API layer
- Never interact with the filesystem directly (delegates to other services)
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.constants import SIGNATURE_PREFIX, HMAC_ALGORITHM
from app.models.webhook import WebhookPayload
from services.git_service import GitService
from services.parser_service import ParserService
from services.repository_service import RepositoryService
from services.workflow_service import WorkflowService
from workflow.workflow_state import WorkflowState

logger = logging.getLogger(__name__)


@dataclass
class WebhookProcessingResult:
    """Returned by GitHubService.process_push_event().

    Attributes:
        workflow_id: UUID of the workflow that was created.
        repository:  Short repository name.
        branch:      Branch that was pushed to.
    """

    workflow_id: str
    repository: str
    branch: str


class GitHubService:
    """Orchestrates the complete GitHub push webhook processing pipeline.

    Args:
        git_service:        GitService instance for clone/pull operations.
        parser_service:     ParserService instance for commit parsing.
        workflow_service:   WorkflowService instance for state management.
        repository_service: RepositoryService instance for path resolution.
        coordinator:        Agent pipeline coordinator.
        github_secret:      Optional HMAC secret for signature verification.
        rag_service:        Optional RAGService for incremental indexing and
                            retrieval. When provided, the RAG pipeline runs
                            after git sync and the resulting ContextPackage
                            is forwarded to the coordinator so agents have
                            real code context. When None the pipeline degrades
                            gracefully to metadata-only agent reasoning.
    """

    def __init__(
        self,
        git_service: GitService,
        parser_service: ParserService,
        workflow_service: WorkflowService,
        repository_service: RepositoryService,
        coordinator,
        github_secret: str = "",
        rag_service=None,
    ) -> None:
        self._git_service = git_service
        self._parser_service = parser_service
        self._workflow_service = workflow_service
        self._repository_service = repository_service
        self._coordinator = coordinator
        self._github_secret = github_secret
        self._rag_service = rag_service

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def verify_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verify the HMAC-SHA256 signature sent by GitHub.

        If no secret is configured, verification is skipped and True is
        returned so the service can operate in development mode without a secret.

        Args:
            raw_body:         Raw request body bytes.
            signature_header: Value of the ``X-Hub-Signature-256`` header.

        Returns:
            bool: True if the signature is valid (or verification is disabled).
        """
        if not self._github_secret:
            logger.warning("GitHub secret not configured — skipping signature verification")
            return True

        if not signature_header.startswith(SIGNATURE_PREFIX):
            logger.warning("Signature header missing 'sha256=' prefix")
            return False

        received_sig = signature_header[len(SIGNATURE_PREFIX):]
        expected_sig = hmac.new(
            self._github_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=HMAC_ALGORITHM,
        ).hexdigest()

        valid = hmac.compare_digest(received_sig, expected_sig)
        if valid:
            logger.info("Webhook signature validated successfully")
        else:
            logger.warning("Webhook signature mismatch — request rejected")
        return valid

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def process_push_event(self, payload: WebhookPayload) -> WebhookProcessingResult:
        """Execute the full push-event processing pipeline.

        Steps:
        1. Extract repository information from the payload.
        2. Resolve the local repository path.
        3. Sync repository (clone or pull).
        4. Parse commit metadata and changed files.
        5. Create a workflow, transition it through IN_PROGRESS → COMPLETED
           (or FAILED on error), and persist it.

        Args:
            payload: Validated WebhookPayload from the API layer.

        Returns:
            WebhookProcessingResult: Summary data for the API response.

        Raises:
            RuntimeError: If a Git operation or workflow save fails; the
                          workflow is marked FAILED before re-raising.
        """
        logger.info(
            "Processing push event: repo=%s  branch=%s",
            payload.repository.full_name,
            payload.branch,
        )

        # Step 1 – Resolve local path
        slug = payload.repository.owner_repo_slug
        local_path = self._repository_service.get_repository_path(slug)
        self._repository_service.ensure_repository_root()
        logger.info("Repository identified: slug=%s  path=%s", slug, local_path)

        # Step 2 – Parse commit data early so we can create the workflow
        #          even if the Git sync fails
        logger.info("Parsing commit data")
        parsed = self._parser_service.parse(payload)

        # Step 3 – Create workflow (PENDING → IN_PROGRESS)
        state: WorkflowState = self._workflow_service.create_workflow(parsed)

        try:
             # Step 4 – Sync repository (clone or pull)
             logger.info("Syncing repository: %s", local_path)
             self._git_service.sync_repository(
                 clone_url=payload.repository.clone_url,
                 local_path=local_path,
             )

             # Step 5 – Run RAG incremental pipeline (optional)
             # Processes git diff → AST diff → semantic change → updates
             # FAISS/BM25/dependency-graph indexes, then retrieves context
             # chunks for the commit. The ContextPackage is forwarded to the
             # coordinator so UnderstandingAgent has grounded code context.
             context_package: Optional[object] = None
             if self._rag_service is not None:
                 logger.info(
                     "Running RAG incremental pipeline: %s (%s → %s)",
                     payload.repository.full_name,
                     payload.before,
                     payload.after,
                 )
                 try:
                     rag_result = self._rag_service.run_incremental(
                         repo_path=local_path,
                         repo_name=payload.repository.full_name,
                         old_sha=payload.before,
                         new_sha=payload.after,
                         workflow_id=state.workflow_id,
                     )
                     if rag_result is not None and rag_result.success:
                         context_package = rag_result.context_package
                         logger.info(
                             "RAG pipeline succeeded: %d chunk(s) retrieved",
                             context_package.metadata.total_retrieved_chunks
                             if context_package
                             else 0,
                         )
                     else:
                         logger.warning(
                             "RAG pipeline did not succeed — "
                             "proceeding with metadata-only agent reasoning"
                         )
                 except Exception as rag_exc:
                     logger.warning(
                         "RAG pipeline raised an exception — "
                         "proceeding with metadata-only agent reasoning: %s",
                         rag_exc,
                     )
             else:
                 logger.info(
                     "RAG service not configured — "
                     "agents will reason from metadata only"
                 )

             # Step 6 – Trigger agentic AI workflow to generate documentation
             logger.info("Triggering Agentic AI documentation workflow")
             summary = self._coordinator.start_workflow(
                 repository_name=payload.repository.full_name,
                 repository_path=local_path,
                 branch=payload.branch,
                 commit_sha=payload.after,
                 workflow_id=state.workflow_id,
                 added_files=parsed.added_files,
                 modified_files=parsed.modified_files,
                 author=parsed.author,
                 push_timestamp=parsed.commit_timestamp,
                 context_package=context_package,
             )

             if summary.status != "COMPLETED":
                 raise RuntimeError(summary.error_message or "Agentic workflow failed")

             # Step 7 – Mark webhook workflow as completed
             self._workflow_service.complete_workflow(state)
             logger.info("Push event processed successfully: workflow_id=%s", state.workflow_id)

        except RuntimeError as exc:
            logger.error("Pipeline error for workflow_id=%s: %s", state.workflow_id, exc)
            self._workflow_service.fail_workflow(state, str(exc))
            raise

        return WebhookProcessingResult(
            workflow_id=state.workflow_id,
            repository=payload.repository.name,
            branch=payload.branch,
        )
