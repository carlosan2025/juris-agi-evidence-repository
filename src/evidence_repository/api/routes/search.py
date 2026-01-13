"""Search endpoints for semantic document search."""

import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pgvector.sqlalchemy import Vector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from evidence_repository.api.dependencies import User, get_current_user
from evidence_repository.db.session import get_db_session
from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
from evidence_repository.models.document import Document, DocumentVersion
from evidence_repository.models.embedding import EmbeddingChunk
from evidence_repository.models.project import Project, ProjectDocument
from evidence_repository.schemas.search import SearchQuery, SearchResult, SearchResultItem

router = APIRouter()


@router.post(
    "",
    response_model=SearchResult,
    summary="Semantic Search",
    description="Perform semantic search across all documents or within specific scope.",
)
async def search_documents(
    query: SearchQuery,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SearchResult:
    """Perform semantic search using vector similarity.

    Uses pgvector for efficient similarity search against document embeddings.
    """
    start_time = time.time()

    # Generate query embedding
    embedding_client = OpenAIEmbeddingClient()
    try:
        query_embedding = await embedding_client.embed_text(query.query)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to generate query embedding: {e}",
        )

    # Build search query with vector similarity
    # Using cosine distance: 1 - cosine_similarity
    # pgvector uses <=> for cosine distance
    similarity_col = (1 - EmbeddingChunk.embedding.cosine_distance(query_embedding)).label(
        "similarity"
    )

    search_query = (
        select(
            EmbeddingChunk,
            similarity_col,
        )
        .options(
            selectinload(EmbeddingChunk.document_version).selectinload(
                DocumentVersion.document
            )
        )
        .where(
            similarity_col >= query.similarity_threshold,
        )
        .order_by(similarity_col.desc())
        .limit(query.limit)
    )

    # Filter by project if specified
    if query.project_id:
        # Get document IDs in project
        project_docs = await db.execute(
            select(ProjectDocument.document_id).where(
                ProjectDocument.project_id == query.project_id
            )
        )
        doc_ids = [row[0] for row in project_docs.fetchall()]

        if not doc_ids:
            return SearchResult(
                query=query.query,
                results=[],
                total=0,
                search_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.utcnow(),
            )

        # Filter by document versions belonging to project documents
        version_ids_query = select(DocumentVersion.id).where(
            DocumentVersion.document_id.in_(doc_ids)
        )
        search_query = search_query.where(
            EmbeddingChunk.document_version_id.in_(version_ids_query)
        )

    # Filter by specific documents if specified
    if query.document_ids:
        version_ids_query = select(DocumentVersion.id).where(
            DocumentVersion.document_id.in_(query.document_ids)
        )
        search_query = search_query.where(
            EmbeddingChunk.document_version_id.in_(version_ids_query)
        )

    # Execute search
    result = await db.execute(search_query)
    rows = result.fetchall()

    # Build results
    search_results: list[SearchResultItem] = []
    for chunk, similarity in rows:
        doc_version = chunk.document_version
        document = doc_version.document

        search_results.append(
            SearchResultItem(
                chunk_id=chunk.id,
                document_id=document.id,
                document_version_id=doc_version.id,
                span_id=chunk.span_id,
                text=chunk.text if query.include_text else "",
                similarity=float(similarity),
                chunk_index=chunk.chunk_index,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                document_filename=document.filename,
                document_content_type=document.content_type,
                metadata_=chunk.metadata_,
            )
        )

    return SearchResult(
        query=query.query,
        results=search_results,
        total=len(search_results),
        search_time_ms=(time.time() - start_time) * 1000,
        timestamp=datetime.utcnow(),
    )


@router.post(
    "/projects/{project_id}",
    response_model=SearchResult,
    summary="Search Within Project",
    description="Search documents within a specific project context.",
)
async def search_project(
    project_id: uuid.UUID,
    query: SearchQuery,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SearchResult:
    """Search within a specific project."""
    # Verify project exists
    project_result = await db.execute(select(Project).where(Project.id == project_id))
    if not project_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Override project_id in query and delegate
    query.project_id = project_id
    return await search_documents(query, db, user)
