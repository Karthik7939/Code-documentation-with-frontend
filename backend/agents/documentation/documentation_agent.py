"""
agents/documentation/documentation_agent.py
---------------------------------------------
Documentation Agent — generates per-file Markdown documentation.

Responsibilities:
- Read the list of added/modified files from SharedMemory.repository.
- For each file, read its content from the local repository clone.
- Call the LLM with FILE_DOC_PROMPT to produce a Markdown description.
- Store all per-file docs in SharedMemory.documentation.file_docs.
- Return a standardised AgentResult.

This agent MUST NOT:
- Generate broad project-level documents (README, Architecture, etc.).
- Query the RAG pipeline.
- Validate documentation.
- Save files to disk.
- Revise documentation.
"""

import logging
import time
from pathlib import Path

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import SharedMemory, GeneratedDocumentation
from agents.documentation.markdown_formatter import sanitize_markdown
from prompts.documentation_prompt import FILE_DOC_PROMPT

logger = logging.getLogger(__name__)

# Maximum characters of file content sent to the LLM.
# Large files are truncated to avoid exceeding context limits.
_MAX_FILE_CHARS: int = 12_000


class DocumentationAgent:
    """
    Generates per-file Markdown documentation for every source file that was
    added or modified in the triggering push event.

    Each file is processed independently — a failure on one file does not
    block the others. Failures are collected as warnings.

    Args:
        llm_client: Object implementing generate(prompt: str) -> str.
    """

    def __init__(self, llm_client) -> None:
        self._llm = llm_client

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Generate a Markdown doc for each added/modified file and store in SharedMemory.

        Reads:  shared_memory.repository (path, added_files, modified_files)
        Writes: shared_memory.documentation.file_docs

        Args:
            shared_memory: The shared memory object.

        Returns:
            AgentResult: Success or failure result for the Coordinator.
        """
        start = time.monotonic()
        repo_name = shared_memory.repository.full_name or shared_memory.repository.name

        logger.info("Documentation started: %s", repo_name)

        docs = GeneratedDocumentation()
        warnings: list[str] = []

        added_files = shared_memory.repository.added_files or []
        modified_files = shared_memory.repository.modified_files or []

        # Union: added takes priority; a file in both lists is treated as "Created"
        files_to_document: dict[str, str] = {}  # {relative_path: change_status}
        for f in added_files:
            files_to_document[f] = "Created"
        for f in modified_files:
            if f not in files_to_document:
                files_to_document[f] = "Updated"

        if not files_to_document:
            logger.info("No added/modified files in this push — nothing to document")
            shared_memory.documentation = docs
            duration = time.monotonic() - start
            return AgentResult(
                success=True,
                message="Documentation skipped: no added/modified files in this push",
                execution_time=duration,
            )

        logger.info("Generating per-file documentation: %d file(s)", len(files_to_document))
        repo_path = Path(shared_memory.repository.path)
        author = shared_memory.repository.author or "Unknown"
        push_timestamp = shared_memory.repository.push_timestamp or "Unknown"

        for file_path, change_status in files_to_document.items():
            try:
                doc = self._generate_file_doc(
                    repo_path=repo_path,
                    file_path=file_path,
                    change_status=change_status,
                    repo_name=repo_name,
                    author=author,
                    push_timestamp=push_timestamp,
                )
                if doc:
                    docs.file_docs[file_path] = doc
                    logger.info(
                        "File doc generated [%s]: %s (%d chars)",
                        change_status, file_path, len(doc),
                    )
            except Exception as exc:
                warning_msg = f"File doc failed [{file_path}]: {exc}"
                logger.warning(warning_msg)
                warnings.append(warning_msg)

        shared_memory.documentation = docs
        logger.info(
            "Documentation completed: %d file doc(s) generated, %d warning(s)",
            len(docs.file_docs),
            len(warnings),
        )

        duration = time.monotonic() - start
        logger.info("Documentation completed in %.2fs: %s", duration, repo_name)

        if not docs.file_docs:
            return AgentResult(
                success=False,
                message="No file docs were generated (all files skipped or failed)",
                execution_time=duration,
                warnings=warnings,
                recoverable=True,
            )

        return AgentResult(
            success=True,
            message=f"Documentation completed: {len(docs.file_docs)} file doc(s) generated",
            execution_time=duration,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Per-file helpers
    # ------------------------------------------------------------------

    def _generate_file_doc(
        self,
        repo_path: Path,
        file_path: str,
        change_status: str,
        repo_name: str,
        author: str = "Unknown",
        push_timestamp: str = "Unknown",
    ) -> str:
        """Generate a Markdown document for a single source file.

        Args:
            repo_path:      Absolute path to the local repository root.
            file_path:      Relative path of the file within the repository.
            change_status:  "Created" or "Updated" — shown in the prompt.
            repo_name:      Full repository name for the prompt header.
            author:         GitHub username of the developer who made the change.
            push_timestamp: ISO-8601 timestamp of the push event.

        Returns:
            str: Sanitized Markdown content, or empty string if the file
                 cannot be read (binary, missing, or empty).
        """
        abs_path = repo_path / file_path

        if not abs_path.exists():
            logger.warning("File not found in repository clone, skipping: %s", file_path)
            return ""

        if not abs_path.is_file():
            logger.warning("Path is not a file, skipping: %s", file_path)
            return ""

        try:
            raw_content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"Cannot read file {file_path}: {exc}") from exc

        # Truncate very large files to avoid LLM context overflow
        if len(raw_content) > _MAX_FILE_CHARS:
            raw_content = (
                raw_content[:_MAX_FILE_CHARS]
                + "\n\n[... file truncated for documentation ...]"
            )

        if not raw_content.strip():
            logger.info("Empty file, skipping doc generation: %s", file_path)
            return ""

        prompt = FILE_DOC_PROMPT.format(
            repository_name=repo_name,
            file_path=file_path,
            change_status=change_status,
            file_content=raw_content,
            author=author,
            push_timestamp=push_timestamp,
        )

        raw = self._llm.generate(prompt)
        return sanitize_markdown(raw)
