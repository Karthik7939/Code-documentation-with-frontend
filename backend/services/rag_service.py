"""
services/rag_service.py
------------------------
RAG Service — adapter between the ``rag/`` module and the agent pipeline.

Responsibilities:
- Expose ``index_repository(repo_path)`` for full bootstrap indexing.
- Expose ``retrieve(query)`` returning an object with a ``.context`` string
  so that ``UnderstandingAgent`` (which calls ``self._rag.retrieve(query)``)
  works without any changes to its internal contract.
- Expose ``run_incremental(...)`` which wraps ``RAGPipeline`` for commit-level
  incremental index updates and returns a ``PipelineResult``.

Graceful degradation:
- Every public method catches all exceptions and degrades gracefully.
- A failed index or retrieval never propagates to break the agent pipeline.

This service is intentionally kept thin. Business logic lives in the
``rag/`` subpackages; this class is only responsible for wiring and
error isolation.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retrieval result wrapper
# ---------------------------------------------------------------------------

class _RetrievalResult:
    """
    Thin wrapper returned by RAGService.retrieve().

    Attributes:
        query:   The original query string.
        chunks:  List of RetrievalResult objects (may be empty).
        context: Pre-formatted context string ready to embed in an LLM prompt.
    """

    def __init__(self, query: str, chunks: list, context: str) -> None:
        self.query = query
        self.chunks = chunks
        self.context = context

    @classmethod
    def empty(cls, query: str, reason: str = "") -> "_RetrievalResult":
        """Return a result with no chunks and an explanatory context string."""
        note = f" Reason: {reason}" if reason else ""
        return cls(
            query=query,
            chunks=[],
            context=f"[No RAG context available for: '{query}'.{note}]",
        )


# ---------------------------------------------------------------------------
# RAGService
# ---------------------------------------------------------------------------

class RAGService:
    """
    Adapter layer between the ``rag/`` package and the rest of the backend.

    Usage (in UnderstandingAgent)::

        rag = RAGService()
        rag.index_repository("/path/to/repo")
        result = rag.retrieve("API endpoint handler request response")
        print(result.context)   # formatted text for LLM prompt

    Usage (in GitHubService)::

        rag = RAGService()
        pipeline_result = rag.run_incremental(
            repo_path="/path/to/repo",
            repo_name="owner/repo",
            old_sha="abc123",
            new_sha="def456",
            workflow_id="uuid-here",
        )
        if pipeline_result and pipeline_result.success:
            context_package = pipeline_result.context_package

    Args:
        repository_name: Optional repository name pre-bound to this instance.
                         Can be overridden per-call in ``run_incremental()``.
    """

    def __init__(self, repository_name: Optional[str] = None) -> None:
        self._repository_name = repository_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_repository(self, repo_path: str, commit_sha: str = "HEAD") -> None:
        """
        Perform a full bootstrap index build for a repository.

        Chunks every supported file, generates embeddings, builds FAISS
        and BM25 stores, and constructs the dependency graph.

        Args:
            repo_path:  Absolute or relative path to the cloned repository.
            commit_sha: Commit SHA to tag the index with (default: "HEAD").

        Note:
            Failures are logged but do NOT propagate — the caller continues.
        """
        try:
            from rag.pipeline.bootstrap_pipeline import BootstrapPipeline

            repo_name = self._repository_name or _infer_repo_name(repo_path)
            logger.info("RAGService: starting bootstrap index for '%s'", repo_name)

            pipeline = BootstrapPipeline(
                repository_path=repo_path,
                repository_name=repo_name,
                commit_sha=commit_sha,
            )
            pipeline.run()

            stats = pipeline.statistics()
            logger.info(
                "RAGService: bootstrap complete for '%s' — stats: %s",
                repo_name,
                stats,
            )
        except Exception as exc:
            logger.warning(
                "RAGService.index_repository failed (degrading gracefully): %s", exc
            )

    def retrieve(self, query: str, repository_name: Optional[str] = None) -> _RetrievalResult:
        """
        Retrieve relevant code context for a natural-language query.

        Delegates to ``RetrievalPipeline`` using the FAISS, BM25, and
        dependency-graph stores built by a prior bootstrap or incremental run.

        The returned object always has a ``.context`` string attribute — either
        a formatted block of retrieved code/docs or an explanatory fallback
        message.

        Args:
            query:           Natural-language query string.
            repository_name: Repository to search (falls back to instance default).

        Returns:
            _RetrievalResult: Object with .chunks and .context attributes.
        """
        try:
            from rag.pipeline.retrieval_pipeline import RetrievalPipeline
            from rag.schemas.query import SemanticQuery

            repo_name = repository_name or self._repository_name or ""

            semantic_query = SemanticQuery(
                repository=repo_name,
                commit_sha="",
                query_text=query,
            )

            pipeline = RetrievalPipeline()
            context_package = pipeline.retrieve(semantic_query)

            if not context_package.has_context:
                logger.debug(
                    "RAGService.retrieve: no chunks retrieved for query '%s'", query
                )
                return _RetrievalResult.empty(query, "No matching chunks in index")

            context_str = _format_context(context_package)
            chunks = list(context_package.retrieval_results.results)

            logger.debug(
                "RAGService.retrieve: %d chunk(s) for query '%s'",
                len(chunks),
                query,
            )
            return _RetrievalResult(query=query, chunks=chunks, context=context_str)

        except Exception as exc:
            logger.warning(
                "RAGService.retrieve failed (degrading gracefully): %s", exc
            )
            return _RetrievalResult.empty(query, str(exc))

    def run_incremental(
        self,
        repo_path: str,
        repo_name: str,
        old_sha: Optional[str],
        new_sha: str,
        workflow_id: Optional[str] = None,
    ):
        """
        Run an incremental RAG pipeline for a commit-level change.

        Performs Git + AST diff analysis, updates the FAISS/BM25/graph
        indexes, and returns a retrieval context package for the change.

        Args:
            repo_path:   Absolute or relative path to the cloned repository.
            repo_name:   Full repository name, e.g. ``'owner/repo'``.
            old_sha:     Commit SHA before the push (``payload.before``).
            new_sha:     Commit SHA after the push (``payload.after``).
            workflow_id: Optional workflow UUID for progress event logging.

        Returns:
            PipelineResult | None: Contains ``.success`` and
            ``.context_package`` on success; ``None`` on fatal error.
        """
        try:
            from rag.pipeline.rag_pipeline import RAGPipeline

            logger.info(
                "RAGService: running incremental pipeline for '%s' (%s → %s)",
                repo_name,
                old_sha,
                new_sha,
            )

            pipeline = RAGPipeline(
                repository_path=repo_path,
                repository_name=repo_name,
            )
            result = pipeline.run(
                old_commit_sha=old_sha,
                new_commit_sha=new_sha,
                workflow_id=workflow_id,
            )

            if result.success:
                logger.info(
                    "RAGService: incremental pipeline succeeded for '%s' "
                    "(%.2fms, %d chunk(s) retrieved)",
                    repo_name,
                    result.execution_time_ms,
                    result.context_package.metadata.total_retrieved_chunks
                    if result.context_package
                    else 0,
                )
            else:
                logger.warning(
                    "RAGService: incremental pipeline reported failure for '%s': %s",
                    repo_name,
                    result.error,
                )

            return result

        except Exception as exc:
            logger.warning(
                "RAGService.run_incremental failed (degrading gracefully): %s", exc
            )
            return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _infer_repo_name(repo_path: str) -> str:
    """Derive a best-effort repository name from a filesystem path."""
    from pathlib import Path
    return Path(repo_path).name


def _format_context(context_package) -> str:
    """
    Format a ``ContextPackage`` into a human-readable context block
    suitable for insertion into an LLM prompt.

    Each retrieved chunk is rendered as:

        [File: path/to/file.py | Lines: 10-50 | Source: faiss]
        <code content>
        ---

    Args:
        context_package: A ``ContextPackage`` instance.

    Returns:
        str: Multi-line formatted context string.
    """
    lines: list[str] = []
    results = context_package.retrieval_results.results

    for item in results:
        meta = item.chunk.metadata
        header = (
            f"[File: {meta.file_path}"
            f" | Lines: {meta.start_line}-{meta.end_line}"
            f" | Source: {item.retrieval_source.value}"
            f" | Rank: {item.rank}]"
        )
        if item.retrieval_reason:
            header += f"\n[Reason: {item.retrieval_reason}]"

        lines.append(header)
        lines.append(item.chunk.content)
        lines.append("---")

    return "\n".join(lines) if lines else "[No context retrieved]"
