"""
app/api/rag.py
---------------
RAG (Retrieval Augmented Generation) API endpoints.

Exposes two HTTP endpoints:

POST /api/rag/bootstrap
    Trigger a full initial index build for a repository.
    Must be called once after a repository is cloned/synced before any
    incremental pipeline or retrieve calls will return useful results.

POST /api/rag/retrieve
    Synchronous retrieval from pre-built indexes.
    Accepts a SemanticQuery JSON body and returns a ContextPackage JSON body.
    Can be called by external agents or services that need code context
    without triggering a full webhook flow.

No business logic. No filesystem access. Delegates entirely to RAGService
and the underlying rag/ pipelines.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter()

# One shared RAGService instance for all API calls.
# Construction is cheap (no I/O at init time).
_rag_service = RAGService()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BootstrapRequest(BaseModel):
    """Request body for POST /api/rag/bootstrap."""

    repository_name: str = Field(
        ...,
        description="Full repository name, e.g. 'owner/repo'.",
    )
    repository_path: str = Field(
        ...,
        description=(
            "Local filesystem path to the cloned repository. "
            "Must already exist on disk."
        ),
    )
    commit_sha: str = Field(
        default="HEAD",
        description="Commit SHA to tag the index with.",
    )


class BootstrapResponse(BaseModel):
    """Response body for POST /api/rag/bootstrap."""

    status: str
    message: str
    repository_name: str


class RetrieveRequest(BaseModel):
    """
    Request body for POST /api/rag/retrieve.

    Minimum required fields are ``repository``, ``commit_sha``, and
    ``query_text``. All other fields improve retrieval quality but are
    optional for external callers.
    """

    repository: str = Field(
        ...,
        description="Repository name, e.g. 'owner/repo'.",
    )
    commit_sha: str = Field(
        ...,
        description="Commit SHA context for retrieval.",
    )
    query_text: str = Field(
        ...,
        min_length=1,
        description="Natural language retrieval query.",
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="Files modified in the commit (improves filtering).",
    )
    modified_symbols: list[str] = Field(
        default_factory=list,
        description="Function/class/method names modified in the commit.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for BM25 keyword retrieval.",
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of chunks to return.",
    )
    similarity_threshold: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/bootstrap",
    status_code=status.HTTP_200_OK,
    summary="Bootstrap RAG Indexes",
    description=(
        "Builds the full initial FAISS, BM25, and dependency-graph indexes "
        "for a repository from scratch. Run this once after cloning or syncing "
        "a repository. Subsequent GitHub push webhooks will perform incremental "
        "updates automatically."
    ),
    tags=["RAG"],
    response_model=BootstrapResponse,
)
async def bootstrap_repository(request: BootstrapRequest) -> BootstrapResponse:
    """
    Trigger a full index bootstrap for a repository.

    Args:
        request: Bootstrap request with repository_name, repository_path,
                 and optional commit_sha.

    Returns:
        BootstrapResponse: Confirmation with status and repository name.

    Raises:
        HTTPException 500: If the bootstrap pipeline fails fatally.
    """
    logger.info(
        "RAG bootstrap requested: repo=%s  path=%s  sha=%s",
        request.repository_name,
        request.repository_path,
        request.commit_sha,
    )

    try:
        rag = RAGService(repository_name=request.repository_name)
        rag.index_repository(
            repo_path=request.repository_path,
            commit_sha=request.commit_sha,
        )
    except Exception as exc:
        logger.error("RAG bootstrap failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bootstrap failed: {exc}",
        ) from exc

    logger.info("RAG bootstrap completed: repo=%s", request.repository_name)
    return BootstrapResponse(
        status="ok",
        message=(
            f"Bootstrap completed for '{request.repository_name}'. "
            "FAISS, BM25, and dependency-graph indexes are ready."
        ),
        repository_name=request.repository_name,
    )


@router.post(
    "/retrieve",
    status_code=status.HTTP_200_OK,
    summary="Retrieve RAG Context",
    description=(
        "Performs synchronous hybrid retrieval (FAISS + BM25 + dependency graph) "
        "for the given semantic query and returns a ranked ContextPackage. "
        "The repository must have been bootstrapped first. "
        "Can be called by external agents that need code context without "
        "triggering a full GitHub webhook flow."
    ),
    tags=["RAG"],
)
async def retrieve_context(request: RetrieveRequest) -> JSONResponse:
    """
    Perform synchronous hybrid retrieval for a semantic query.

    Args:
        request: RetrieveRequest with repository, commit_sha, and query_text.

    Returns:
        JSONResponse: Serialised ContextPackage with ranked retrieval results.

    Raises:
        HTTPException 500: If retrieval fails fatally.
        HTTPException 404: If no context is found (empty result set).
    """
    logger.info(
        "RAG retrieve requested: repo=%s  sha=%s  query='%s'",
        request.repository,
        request.commit_sha,
        request.query_text[:80],
    )

    try:
        from rag.pipeline.retrieval_pipeline import RetrievalPipeline
        from rag.schemas.query import SemanticQuery

        semantic_query = SemanticQuery(
            repository=request.repository,
            commit_sha=request.commit_sha,
            query_text=request.query_text,
            changed_files=request.changed_files,
            modified_symbols=request.modified_symbols,
            keywords=request.keywords,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )

        pipeline = RetrievalPipeline()
        context_package = pipeline.retrieve(semantic_query)

    except Exception as exc:
        logger.error("RAG retrieve failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {exc}",
        ) from exc

    logger.info(
        "RAG retrieve completed: repo=%s  chunks=%d",
        request.repository,
        context_package.metadata.total_retrieved_chunks,
    )

    # Serialise the Pydantic model to JSON-compatible dict
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=context_package.model_dump(mode="json"),
    )
