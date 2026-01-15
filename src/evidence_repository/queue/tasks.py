"""Background worker tasks for document processing."""

import hashlib
import logging
import mimetypes
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from rq import get_current_job
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from evidence_repository.config import get_settings
from evidence_repository.models.document import Document, DocumentVersion, ExtractionStatus, ProcessingStatus


def _set_processing_status(version: DocumentVersion, status: ProcessingStatus) -> None:
    """Set processing status on a document version."""
    version.processing_status = status


from evidence_repository.queue.jobs import JobManager, JobType, get_job_manager
from evidence_repository.storage import StorageBackend, get_storage_backend

logger = logging.getLogger(__name__)

# Supported MIME types mapping
MIME_TYPE_MAP = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _get_sync_db_session() -> Session:
    """Get synchronous database session for worker tasks.

    Workers run in a separate process and need sync connections.
    """
    settings = get_settings()
    # Convert async URL to sync
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _get_storage() -> StorageBackend:
    """Get storage backend for worker tasks."""
    return get_storage_backend()


def _update_progress(progress: float, message: str | None = None) -> None:
    """Update progress of the current job."""
    job = get_current_job()
    if job:
        job_manager = get_job_manager()
        job_manager.update_progress(job.id, progress, message)


def _compute_file_hash(data: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(data).hexdigest()


# =============================================================================
# Document Processing Tasks
# =============================================================================


def task_ingest_document(
    file_data: bytes,
    filename: str,
    content_type: str,
    metadata: dict | None = None,
    user_id: str | None = None,
) -> dict:
    """Ingest a document into the repository.

    Args:
        file_data: File content as bytes.
        filename: Original filename.
        content_type: MIME type.
        metadata: Optional metadata.
        user_id: User who initiated the upload.

    Returns:
        Dict with document_id and version_id.
    """
    _update_progress(0, "Starting document ingestion")

    settings = get_settings()
    db = _get_sync_db_session()
    storage = _get_storage()

    try:
        file_hash = _compute_file_hash(file_data)
        _update_progress(10, "Computed file hash")

        # Check for duplicate
        existing = db.execute(
            select(Document).where(
                Document.file_hash == file_hash,
                Document.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

        if existing:
            _update_progress(100, "Document already exists (deduplicated)")
            return {
                "document_id": str(existing.id),
                "version_id": str(existing.versions[0].id) if existing.versions else None,
                "deduplicated": True,
            }

        # Create document
        document = Document(
            filename=filename,
            original_filename=filename,
            content_type=content_type,
            file_hash=file_hash,
            metadata_=metadata or {},
        )
        db.add(document)
        db.flush()
        _update_progress(30, "Created document record")

        # Generate storage path
        version_number = 1
        storage_path = f"documents/{document.id}/v{version_number}/{filename}"

        # Upload to storage synchronously
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                storage.upload(storage_path, file_data, content_type)
            )
        finally:
            loop.close()
        _update_progress(60, "Uploaded file to storage")

        # Create version
        version = DocumentVersion(
            document_id=document.id,
            version_number=version_number,
            storage_path=storage_path,
            file_size=len(file_data),
            file_hash=file_hash,
            extraction_status=ExtractionStatus.PENDING,
            metadata_={"uploaded_by": user_id} if user_id else {},
        )
        db.add(version)
        db.commit()
        _update_progress(100, "Document ingested successfully")

        return {
            "document_id": str(document.id),
            "version_id": str(version.id),
            "deduplicated": False,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Document ingestion failed: {e}")
        raise
    finally:
        db.close()


def task_extract_document(
    document_id: str,
    version_id: str | None = None,
) -> dict:
    """Extract text from a document.

    Args:
        document_id: Document ID.
        version_id: Optional specific version ID (defaults to latest).

    Returns:
        Dict with extraction results.
    """
    _update_progress(0, "Starting text extraction")

    db = _get_sync_db_session()
    storage = _get_storage()

    try:
        # Get document and version
        doc_uuid = uuid.UUID(document_id)
        document = db.execute(
            select(Document).where(Document.id == doc_uuid)
        ).scalar_one_or_none()

        if not document:
            raise ValueError(f"Document {document_id} not found")

        if version_id:
            version = db.execute(
                select(DocumentVersion).where(DocumentVersion.id == uuid.UUID(version_id))
            ).scalar_one_or_none()
        else:
            version = db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc_uuid)
                .order_by(DocumentVersion.version_number.desc())
            ).scalars().first()

        if not version:
            raise ValueError(f"No version found for document {document_id}")

        _update_progress(10, "Found document version")

        # Update status
        version.extraction_status = ExtractionStatus.PROCESSING
        db.flush()

        # Download file content
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            file_data = loop.run_until_complete(storage.download(version.storage_path))
        finally:
            loop.close()
        _update_progress(30, "Downloaded file from storage")

        # Extract based on content type
        text = ""
        page_count = None

        if document.content_type == "application/pdf":
            text, page_count = _extract_pdf_text(file_data)
        elif document.content_type in ["text/plain", "text/markdown", "text/csv"]:
            text = _extract_text_content(file_data)
        elif document.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            text = _extract_xlsx_text(file_data)
        elif document.content_type.startswith("image/"):
            text = _extract_image_text(file_data, document.content_type)
        else:
            raise ValueError(f"Unsupported content type: {document.content_type}")

        _update_progress(80, "Extracted text content")

        # Update version
        version.extracted_text = text
        version.extraction_status = ExtractionStatus.COMPLETED
        version.extracted_at = datetime.utcnow()
        version.page_count = page_count
        version.extraction_error = None
        db.commit()

        _update_progress(100, "Extraction completed successfully")

        return {
            "document_id": document_id,
            "version_id": str(version.id),
            "text_length": len(text),
            "page_count": page_count,
        }

    except Exception as e:
        if version:
            version.extraction_status = ExtractionStatus.FAILED
            version.extraction_error = str(e)
            db.commit()
        logger.error(f"Extraction failed for {document_id}: {e}")
        raise
    finally:
        db.close()


def task_embed_document(
    document_id: str,
    version_id: str | None = None,
    embed_spans: bool = True,
    reprocess: bool = False,
) -> dict:
    """Generate embeddings for a document.

    Embeds text spans first if available, otherwise falls back to text chunking.
    Only embeds text-type spans (TEXT, HEADING, CITATION, FOOTNOTE).

    Args:
        document_id: Document ID.
        version_id: Optional specific version ID.
        embed_spans: If True, embed spans first (default). If False, use text chunking.
        reprocess: If True, delete existing embeddings before generating new ones.

    Returns:
        Dict with embedding results.
    """
    _update_progress(0, "Starting embedding generation")

    # Import here to avoid circular imports
    from evidence_repository.embeddings.chunker import TextChunker
    from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
    from evidence_repository.models.embedding import EmbeddingChunk
    from evidence_repository.models.evidence import Span, SpanType

    settings = get_settings()
    db = _get_sync_db_session()

    # Embeddable span types (text-based spans only)
    EMBEDDABLE_SPAN_TYPES = {SpanType.TEXT, SpanType.HEADING, SpanType.CITATION, SpanType.FOOTNOTE}

    try:
        # Get version with extracted text
        doc_uuid = uuid.UUID(document_id)

        if version_id:
            version = db.execute(
                select(DocumentVersion).where(DocumentVersion.id == uuid.UUID(version_id))
            ).scalar_one_or_none()
        else:
            version = db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc_uuid)
                .order_by(DocumentVersion.version_number.desc())
            ).scalars().first()

        if not version:
            raise ValueError(f"No version found for document {document_id}")

        _update_progress(10, "Found document version")

        # Delete existing embeddings if reprocessing
        if reprocess:
            deleted = db.execute(
                EmbeddingChunk.__table__.delete().where(
                    EmbeddingChunk.document_version_id == version.id
                )
            )
            db.flush()
            logger.info(f"Deleted existing embeddings for version {version.id}")

        # Try to embed spans first
        if embed_spans:
            spans = db.execute(
                select(Span)
                .where(
                    Span.document_version_id == version.id,
                    Span.span_type.in_(EMBEDDABLE_SPAN_TYPES),
                )
                .order_by(Span.created_at)
            ).scalars().all()

            if spans:
                _update_progress(15, f"Found {len(spans)} text spans to embed")
                result = _embed_spans_sync(db, version, list(spans), reprocess)
                db.commit()
                _update_progress(100, "Span embeddings completed")
                return result

        # Fall back to text chunking if no spans or embed_spans=False
        if not version.extracted_text:
            raise ValueError(f"Document {document_id} has no extracted text and no spans")

        _update_progress(20, "No spans found, falling back to text chunking")

        # Chunk the text
        chunker = TextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        chunks = chunker.chunk_text(version.extracted_text)
        _update_progress(30, f"Created {len(chunks)} text chunks")

        if not chunks:
            return {
                "document_id": document_id,
                "version_id": str(version.id),
                "chunks_created": 0,
                "mode": "chunking",
            }

        # Generate embeddings using synchronous approach
        client = OpenAIEmbeddingClient()
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            texts = [c.text for c in chunks]
            embeddings = loop.run_until_complete(client.embed_texts(texts))
        finally:
            loop.close()

        _update_progress(70, "Generated embeddings")

        # Delete existing non-span embeddings for this version (if not already done)
        if not reprocess:
            db.execute(
                EmbeddingChunk.__table__.delete().where(
                    EmbeddingChunk.document_version_id == version.id,
                    EmbeddingChunk.span_id.is_(None),  # Only delete chunk-based embeddings
                )
            )

        # Store embedding chunks
        for chunk, embedding in zip(chunks, embeddings):
            embedding_chunk = EmbeddingChunk(
                document_version_id=version.id,
                chunk_index=chunk.index,
                text=chunk.text,
                embedding=embedding,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                metadata_=chunk.metadata,
            )
            db.add(embedding_chunk)

        db.commit()
        _update_progress(100, "Embeddings stored successfully")

        return {
            "document_id": document_id,
            "version_id": str(version.id),
            "chunks_created": len(chunks),
            "mode": "chunking",
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Embedding generation failed for {document_id}: {e}")
        raise
    finally:
        db.close()


def _embed_spans_sync(
    db: Session,
    version: DocumentVersion,
    spans: list,
    reprocess: bool = False,
) -> dict:
    """Embed spans synchronously with retry logic.

    Args:
        db: Database session.
        version: Document version.
        spans: List of Span objects to embed.
        reprocess: If True, re-embed existing spans.

    Returns:
        Dict with embedding results.
    """
    from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
    from evidence_repository.models.embedding import EmbeddingChunk

    BATCH_SIZE = 50

    # Filter spans with content and check for existing embeddings
    valid_spans = []
    existing_span_ids: set = set()

    if not reprocess:
        # Check which spans already have embeddings
        span_ids = [s.id for s in spans]
        result = db.execute(
            select(EmbeddingChunk.span_id)
            .where(EmbeddingChunk.span_id.in_(span_ids))
        )
        existing_span_ids = {row[0] for row in result.fetchall()}

    for span in spans:
        if span.id in existing_span_ids:
            continue
        if not span.text_content or not span.text_content.strip():
            continue
        valid_spans.append(span)

    if not valid_spans:
        return {
            "document_id": str(version.document_id),
            "version_id": str(version.id),
            "spans_embedded": 0,
            "spans_skipped": len(spans),
            "mode": "spans",
        }

    # Generate embeddings in batches
    client = OpenAIEmbeddingClient()
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    all_chunks = []

    try:
        for batch_start in range(0, len(valid_spans), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(valid_spans))
            batch_spans = valid_spans[batch_start:batch_end]

            # Progress update
            progress = 15 + ((batch_start / len(valid_spans)) * 70)
            _update_progress(progress, f"Embedding batch {batch_start // BATCH_SIZE + 1}")

            # Generate embeddings
            texts = [s.text_content for s in batch_spans]
            embeddings = loop.run_until_complete(client.embed_texts(texts))

            # Create embedding chunks
            for span, embedding, idx in zip(batch_spans, embeddings, range(len(batch_spans))):
                chunk = EmbeddingChunk(
                    document_version_id=version.id,
                    span_id=span.id,
                    chunk_index=idx,
                    text=span.text_content,
                    embedding=embedding,
                    metadata_={
                        "span_type": span.span_type.value,
                        "span_hash": span.span_hash,
                        "locator": span.start_locator,
                    },
                )
                db.add(chunk)
                all_chunks.append(chunk)

    finally:
        loop.close()

    logger.info(
        f"Created {len(all_chunks)} span embeddings for version {version.id} "
        f"(tokens used: {client.get_token_usage()})"
    )

    return {
        "document_id": str(version.document_id),
        "version_id": str(version.id),
        "spans_embedded": len(all_chunks),
        "spans_skipped": len(spans) - len(valid_spans),
        "tokens_used": client.get_token_usage(),
        "mode": "spans",
    }


def task_reembed_version(version_id: str) -> dict:
    """Re-embed all spans for a document version.

    Deletes existing embeddings and regenerates them.

    Args:
        version_id: Document version ID.

    Returns:
        Dict with re-embedding results.
    """
    _update_progress(0, "Starting re-embedding")

    from evidence_repository.models.embedding import EmbeddingChunk

    db = _get_sync_db_session()

    try:
        ver_uuid = uuid.UUID(version_id)

        # Get version
        version = db.execute(
            select(DocumentVersion).where(DocumentVersion.id == ver_uuid)
        ).scalar_one_or_none()

        if not version:
            raise ValueError(f"Version {version_id} not found")

        # Delete existing embeddings
        deleted = db.execute(
            EmbeddingChunk.__table__.delete().where(
                EmbeddingChunk.document_version_id == ver_uuid
            )
        )
        deleted_count = deleted.rowcount
        db.flush()

        _update_progress(20, f"Deleted {deleted_count} existing embeddings")

        # Re-embed using the main embed function
        result = task_embed_document(
            document_id=str(version.document_id),
            version_id=version_id,
            embed_spans=True,
            reprocess=True,
        )

        result["deleted_embeddings"] = deleted_count
        return result

    except Exception as e:
        db.rollback()
        logger.error(f"Re-embedding failed for version {version_id}: {e}")
        raise
    finally:
        db.close()


def task_process_document_full(
    file_data: bytes,
    filename: str,
    content_type: str,
    metadata: dict | None = None,
    user_id: str | None = None,
    skip_embedding: bool = False,
) -> dict:
    """Full document processing pipeline: ingest -> extract -> embed.

    Args:
        file_data: File content.
        filename: Filename.
        content_type: MIME type.
        metadata: Optional metadata.
        user_id: User ID.
        skip_embedding: Skip embedding generation.

    Returns:
        Dict with all processing results.
    """
    result = {"steps": []}

    # Step 1: Ingest
    _update_progress(0, "Step 1/3: Ingesting document")
    ingest_result = task_ingest_document(
        file_data=file_data,
        filename=filename,
        content_type=content_type,
        metadata=metadata,
        user_id=user_id,
    )
    result["ingest"] = ingest_result
    result["steps"].append("ingest")

    # Step 2: Extract
    _update_progress(33, "Step 2/3: Extracting text")
    try:
        extract_result = task_extract_document(
            document_id=ingest_result["document_id"],
            version_id=ingest_result["version_id"],
        )
        result["extract"] = extract_result
        result["steps"].append("extract")
    except Exception as e:
        result["extract_error"] = str(e)
        logger.warning(f"Extraction failed, continuing: {e}")

    # Step 3: Embed (if extraction succeeded)
    if not skip_embedding and "extract" in result:
        _update_progress(66, "Step 3/3: Generating embeddings")
        try:
            embed_result = task_embed_document(
                document_id=ingest_result["document_id"],
                version_id=ingest_result["version_id"],
            )
            result["embed"] = embed_result
            result["steps"].append("embed")
        except Exception as e:
            result["embed_error"] = str(e)
            logger.warning(f"Embedding failed: {e}")

    _update_progress(100, "Processing complete")
    result["document_id"] = ingest_result["document_id"]
    result["version_id"] = ingest_result["version_id"]

    return result


# =============================================================================
# Bulk Ingestion Tasks
# =============================================================================


def task_bulk_folder_ingest(
    folder_path: str,
    recursive: bool = True,
    user_id: str | None = None,
    process_full: bool = True,
) -> dict:
    """Ingest all supported files from a folder.

    Args:
        folder_path: Path to folder to scan.
        recursive: Whether to scan subfolders.
        user_id: User initiating the bulk import.
        process_full: Whether to run full processing (extract + embed).

    Returns:
        Dict with results for each file.
    """
    settings = get_settings()
    supported_extensions = set(settings.supported_extensions)

    folder = Path(folder_path)
    if not folder.exists():
        raise ValueError(f"Folder not found: {folder_path}")
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder_path}")

    _update_progress(0, f"Scanning folder: {folder_path}")

    # Find all supported files
    if recursive:
        files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in supported_extensions]
    else:
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in supported_extensions]

    total_files = len(files)
    if total_files == 0:
        return {
            "folder_path": folder_path,
            "files_found": 0,
            "files_processed": 0,
            "results": [],
        }

    _update_progress(5, f"Found {total_files} files to process")

    results = []
    job_manager = get_job_manager()

    for i, file_path in enumerate(files):
        progress = 5 + (i / total_files) * 90
        _update_progress(progress, f"Processing {i + 1}/{total_files}: {file_path.name}")

        try:
            # Read file
            with open(file_path, "rb") as f:
                file_data = f.read()

            # Determine content type
            extension = file_path.suffix.lower()
            content_type = MIME_TYPE_MAP.get(extension, "application/octet-stream")

            # Process
            if process_full:
                result = task_process_document_full(
                    file_data=file_data,
                    filename=file_path.name,
                    content_type=content_type,
                    metadata={"source_path": str(file_path), "bulk_import": True},
                    user_id=user_id,
                    skip_embedding=False,
                )
            else:
                result = task_ingest_document(
                    file_data=file_data,
                    filename=file_path.name,
                    content_type=content_type,
                    metadata={"source_path": str(file_path), "bulk_import": True},
                    user_id=user_id,
                )

            results.append({
                "file_path": str(file_path),
                "status": "success",
                "result": result,
            })

        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")
            results.append({
                "file_path": str(file_path),
                "status": "error",
                "error": str(e),
            })

    _update_progress(100, f"Completed processing {total_files} files")

    return {
        "folder_path": folder_path,
        "files_found": total_files,
        "files_processed": len([r for r in results if r["status"] == "success"]),
        "files_failed": len([r for r in results if r["status"] == "error"]),
        "results": results,
    }


def task_ingest_from_url(
    url: str,
    filename: str | None = None,
    user_id: str | None = None,
    process_full: bool = True,
) -> dict:
    """Download and ingest a file from a URL.

    Args:
        url: URL to download from.
        filename: Optional filename override.
        user_id: User ID.
        process_full: Whether to run full processing.

    Returns:
        Dict with ingestion results.
    """
    settings = get_settings()

    _update_progress(0, f"Downloading file from URL")

    try:
        # Download file
        with httpx.Client(timeout=settings.url_download_timeout) as client:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()

        file_data = response.content
        _update_progress(40, f"Downloaded {len(file_data)} bytes")

        # Determine filename
        if not filename:
            # Try to get from Content-Disposition header
            cd = response.headers.get("content-disposition", "")
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip('"')
            else:
                # Extract from URL
                from urllib.parse import urlparse
                filename = Path(urlparse(url).path).name or "downloaded_file"

        # Determine content type
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if not content_type or content_type == "application/octet-stream":
            # Guess from extension
            extension = Path(filename).suffix.lower()
            content_type = MIME_TYPE_MAP.get(extension, "application/octet-stream")

        # Check if supported
        extension = Path(filename).suffix.lower()
        if extension not in settings.supported_extensions:
            raise ValueError(f"Unsupported file type: {extension}")

        # Check file size
        max_size = settings.max_file_size_mb * 1024 * 1024
        if len(file_data) > max_size:
            raise ValueError(f"File too large: {len(file_data)} bytes (max {max_size})")

        _update_progress(50, "Processing downloaded file")

        # Process
        if process_full:
            result = task_process_document_full(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                metadata={"source_url": url, "url_import": True},
                user_id=user_id,
            )
        else:
            result = task_ingest_document(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                metadata={"source_url": url, "url_import": True},
                user_id=user_id,
            )

        _update_progress(100, "URL ingestion complete")

        return {
            "url": url,
            "filename": filename,
            "content_type": content_type,
            "file_size": len(file_data),
            "result": result,
        }

    except httpx.HTTPError as e:
        raise ValueError(f"Failed to download URL: {e}")


# =============================================================================
# Text Extraction Helpers
# =============================================================================


def _extract_pdf_text(data: bytes) -> tuple[str, int]:
    """Extract text from PDF using pypdf."""
    import pypdf
    import io

    reader = pypdf.PdfReader(io.BytesIO(data))
    text_parts = []

    for page in reader.pages:
        text = page.extract_text() or ""
        text_parts.append(text)

    return "\n\n".join(text_parts), len(reader.pages)


def _extract_text_content(data: bytes) -> str:
    """Extract text from plain text files."""
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_xlsx_text(data: bytes) -> str:
    """Extract text from Excel files."""
    import openpyxl
    import io

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    text_parts = []

    for sheet in wb.worksheets:
        sheet_text = [f"=== Sheet: {sheet.title} ==="]
        for row in sheet.iter_rows(values_only=True):
            row_text = [str(cell) if cell is not None else "" for cell in row]
            if any(row_text):
                sheet_text.append("\t".join(row_text))
        text_parts.append("\n".join(sheet_text))

    return "\n\n".join(text_parts)


def _extract_image_text(data: bytes, content_type: str) -> str:
    """Extract text from images using OCR.

    Note: This is a placeholder. For real OCR, integrate Tesseract or a cloud OCR service.
    """
    # For now, just return a placeholder
    # In production, use pytesseract or cloud OCR
    return f"[Image content - {content_type}. OCR not implemented in this version.]"


# =============================================================================
# Batch Ingestion Tasks (with progress tracking)
# =============================================================================


def task_batch_folder_ingest(
    batch_id: str,
    folder_path: str,
    project_id: str | None = None,
    auto_process: bool = True,
    user_id: str | None = None,
) -> dict:
    """Process a folder ingestion batch with item-level tracking.

    This task processes each file in the batch, updating the ingestion_items
    table with progress and results.

    Args:
        batch_id: ID of the ingestion batch.
        folder_path: Path to the folder.
        project_id: Optional project to attach documents to.
        auto_process: Whether to auto-process documents.
        user_id: User initiating the ingestion.

    Returns:
        Dict with batch results.
    """
    from evidence_repository.models.ingestion import (
        IngestionBatch,
        IngestionBatchStatus,
        IngestionItem,
        IngestionItemStatus,
    )
    from evidence_repository.models.project import ProjectDocument

    db = _get_sync_db_session()
    storage = _get_storage()

    try:
        # Get batch
        batch_uuid = uuid.UUID(batch_id)
        batch = db.execute(
            select(IngestionBatch).where(IngestionBatch.id == batch_uuid)
        ).scalar_one_or_none()

        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        # Get all items
        items = db.execute(
            select(IngestionItem)
            .where(IngestionItem.batch_id == batch_uuid)
            .order_by(IngestionItem.created_at)
        ).scalars().all()

        total_items = len(items)
        if total_items == 0:
            batch.status = IngestionBatchStatus.COMPLETED
            batch.completed_at = datetime.utcnow()
            db.commit()
            return {"batch_id": batch_id, "items_processed": 0}

        # Update batch status
        batch.status = IngestionBatchStatus.PROCESSING
        batch.started_at = datetime.utcnow()
        db.flush()

        _update_progress(0, f"Processing {total_items} files")

        processed = 0
        successful = 0
        failed = 0
        skipped = 0

        for i, item in enumerate(items):
            progress = (i / total_items) * 100
            _update_progress(progress, f"Processing {i + 1}/{total_items}: {item.source_filename}")

            try:
                item.status = IngestionItemStatus.PROCESSING
                item.started_at = datetime.utcnow()
                item.attempts += 1
                db.flush()

                # Read file
                file_path = Path(item.source_path)
                if not file_path.exists():
                    item.status = IngestionItemStatus.FAILED
                    item.error_message = f"File not found: {item.source_path}"
                    item.error_code = "FILE_NOT_FOUND"
                    item.completed_at = datetime.utcnow()
                    failed += 1
                    db.flush()
                    continue

                with open(file_path, "rb") as f:
                    file_data = f.read()

                # Compute hash and check for duplicates
                file_hash = _compute_file_hash(file_data)
                item.file_hash = file_hash

                existing = db.execute(
                    select(Document).where(
                        Document.file_hash == file_hash,
                        Document.deleted_at.is_(None),
                    )
                ).scalar_one_or_none()

                if existing:
                    # Document exists, mark as skipped but still attach to project
                    item.status = IngestionItemStatus.SKIPPED
                    item.document_id = existing.id
                    item.document_version_id = existing.versions[0].id if existing.versions else None
                    item.completed_at = datetime.utcnow()
                    skipped += 1

                    # Attach to project if specified
                    if project_id:
                        _attach_to_project(db, existing.id, uuid.UUID(project_id), user_id)

                    db.flush()
                    continue

                # Determine content type
                extension = file_path.suffix.lower()
                content_type = item.content_type or MIME_TYPE_MAP.get(extension, "application/octet-stream")

                # Process the document
                if auto_process:
                    result = task_process_document_full(
                        file_data=file_data,
                        filename=item.source_filename,
                        content_type=content_type,
                        metadata={"source_path": item.source_path, "batch_id": batch_id},
                        user_id=user_id,
                    )
                else:
                    result = task_ingest_document(
                        file_data=file_data,
                        filename=item.source_filename,
                        content_type=content_type,
                        metadata={"source_path": item.source_path, "batch_id": batch_id},
                        user_id=user_id,
                    )

                # Update item with results
                item.status = IngestionItemStatus.COMPLETED
                item.document_id = uuid.UUID(result["document_id"])
                item.document_version_id = uuid.UUID(result["version_id"]) if result.get("version_id") else None
                item.completed_at = datetime.utcnow()
                successful += 1

                # Attach to project if specified
                if project_id:
                    _attach_to_project(db, item.document_id, uuid.UUID(project_id), user_id)

                db.flush()

            except Exception as e:
                logger.error(f"Failed to process item {item.id}: {e}")
                item.status = IngestionItemStatus.FAILED
                item.error_message = str(e)
                item.error_code = "PROCESSING_ERROR"
                item.completed_at = datetime.utcnow()
                failed += 1
                db.flush()

            processed += 1

            # Update batch progress
            batch.processed_items = processed
            batch.successful_items = successful
            batch.failed_items = failed
            batch.skipped_items = skipped
            db.flush()

        # Determine final batch status
        if failed == 0 and skipped == 0:
            batch.status = IngestionBatchStatus.COMPLETED
        elif successful == 0 and failed == total_items:
            batch.status = IngestionBatchStatus.FAILED
        else:
            batch.status = IngestionBatchStatus.PARTIAL

        batch.completed_at = datetime.utcnow()
        db.commit()

        _update_progress(100, f"Batch completed: {successful} succeeded, {failed} failed, {skipped} skipped")

        return {
            "batch_id": batch_id,
            "total_items": total_items,
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Batch folder ingestion failed: {e}")

        # Update batch status
        try:
            batch = db.execute(
                select(IngestionBatch).where(IngestionBatch.id == uuid.UUID(batch_id))
            ).scalar_one_or_none()
            if batch:
                batch.status = IngestionBatchStatus.FAILED
                batch.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass

        raise
    finally:
        db.close()


def task_batch_url_ingest(
    batch_id: str,
    item_id: str,
    url: str,
    filename: str | None = None,
    project_id: str | None = None,
    auto_process: bool = True,
    user_id: str | None = None,
) -> dict:
    """Process a URL ingestion with item-level tracking.

    Args:
        batch_id: ID of the ingestion batch.
        item_id: ID of the ingestion item.
        url: URL to download from.
        filename: Optional filename override.
        project_id: Optional project to attach to.
        auto_process: Whether to auto-process.
        user_id: User ID.

    Returns:
        Dict with ingestion results.
    """
    from evidence_repository.models.ingestion import (
        IngestionBatch,
        IngestionBatchStatus,
        IngestionItem,
        IngestionItemStatus,
    )
    from evidence_repository.utils.security import validate_url_for_ssrf, SSRFProtectionError

    settings = get_settings()
    db = _get_sync_db_session()

    try:
        # Get batch and item
        batch_uuid = uuid.UUID(batch_id)
        item_uuid = uuid.UUID(item_id)

        batch = db.execute(
            select(IngestionBatch).where(IngestionBatch.id == batch_uuid)
        ).scalar_one_or_none()

        item = db.execute(
            select(IngestionItem).where(IngestionItem.id == item_uuid)
        ).scalar_one_or_none()

        if not batch or not item:
            raise ValueError(f"Batch {batch_id} or item {item_id} not found")

        # Update statuses
        batch.status = IngestionBatchStatus.PROCESSING
        batch.started_at = datetime.utcnow()
        item.status = IngestionItemStatus.DOWNLOADING
        item.started_at = datetime.utcnow()
        item.attempts += 1
        db.flush()

        _update_progress(0, "Validating URL")

        # SSRF protection
        try:
            validate_url_for_ssrf(url)
        except SSRFProtectionError as e:
            item.status = IngestionItemStatus.FAILED
            item.error_message = f"URL validation failed: {e}"
            item.error_code = "SSRF_BLOCKED"
            item.completed_at = datetime.utcnow()
            batch.status = IngestionBatchStatus.FAILED
            batch.failed_items = 1
            batch.processed_items = 1
            batch.completed_at = datetime.utcnow()
            db.commit()
            raise ValueError(f"URL validation failed: {e}")

        _update_progress(10, "Downloading file")

        # Download file
        try:
            with httpx.Client(timeout=settings.url_download_timeout) as client:
                response = client.get(url, follow_redirects=True)
                response.raise_for_status()

            file_data = response.content
        except httpx.HTTPError as e:
            item.status = IngestionItemStatus.FAILED
            item.error_message = f"Download failed: {e}"
            item.error_code = "DOWNLOAD_ERROR"
            item.completed_at = datetime.utcnow()
            batch.status = IngestionBatchStatus.FAILED
            batch.failed_items = 1
            batch.processed_items = 1
            batch.completed_at = datetime.utcnow()
            db.commit()
            raise ValueError(f"Download failed: {e}")

        item.source_size = len(file_data)
        item.status = IngestionItemStatus.PROCESSING
        db.flush()

        _update_progress(40, f"Downloaded {len(file_data)} bytes")

        # Check file size
        max_size = settings.max_file_size_mb * 1024 * 1024
        if len(file_data) > max_size:
            item.status = IngestionItemStatus.FAILED
            item.error_message = f"File too large: {len(file_data)} bytes (max {max_size})"
            item.error_code = "FILE_TOO_LARGE"
            item.completed_at = datetime.utcnow()
            batch.status = IngestionBatchStatus.FAILED
            batch.failed_items = 1
            batch.processed_items = 1
            batch.completed_at = datetime.utcnow()
            db.commit()
            raise ValueError(f"File too large: {len(file_data)} bytes")

        # Determine filename if not provided
        if not filename:
            cd = response.headers.get("content-disposition", "")
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip('"')
            else:
                from urllib.parse import urlparse
                filename = Path(urlparse(url).path).name or "downloaded_file"

        item.source_filename = filename

        # Determine content type
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if not content_type or content_type == "application/octet-stream":
            extension = Path(filename).suffix.lower()
            content_type = MIME_TYPE_MAP.get(extension, "application/octet-stream")

        item.content_type = content_type

        # Check if supported
        extension = Path(filename).suffix.lower()
        if extension not in settings.supported_extensions:
            item.status = IngestionItemStatus.FAILED
            item.error_message = f"Unsupported file type: {extension}"
            item.error_code = "UNSUPPORTED_TYPE"
            item.completed_at = datetime.utcnow()
            batch.status = IngestionBatchStatus.FAILED
            batch.failed_items = 1
            batch.processed_items = 1
            batch.completed_at = datetime.utcnow()
            db.commit()
            raise ValueError(f"Unsupported file type: {extension}")

        # Compute hash
        file_hash = _compute_file_hash(file_data)
        item.file_hash = file_hash
        db.flush()

        _update_progress(50, "Processing document")

        # Process
        if auto_process:
            result = task_process_document_full(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                metadata={"source_url": url, "batch_id": batch_id},
                user_id=user_id,
            )
        else:
            result = task_ingest_document(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                metadata={"source_url": url, "batch_id": batch_id},
                user_id=user_id,
            )

        # Update item with results
        item.status = IngestionItemStatus.COMPLETED
        item.document_id = uuid.UUID(result["document_id"])
        item.document_version_id = uuid.UUID(result["version_id"]) if result.get("version_id") else None
        item.completed_at = datetime.utcnow()

        # Attach to project if specified
        if project_id:
            _attach_to_project(db, item.document_id, uuid.UUID(project_id), user_id)

        # Update batch
        batch.status = IngestionBatchStatus.COMPLETED
        batch.successful_items = 1
        batch.processed_items = 1
        batch.completed_at = datetime.utcnow()
        db.commit()

        _update_progress(100, "URL ingestion complete")

        return {
            "batch_id": batch_id,
            "item_id": item_id,
            "url": url,
            "filename": filename,
            "document_id": result["document_id"],
            "version_id": result.get("version_id"),
        }

    except Exception as e:
        db.rollback()
        logger.error(f"URL ingestion failed: {e}")

        # Update statuses
        try:
            batch = db.execute(
                select(IngestionBatch).where(IngestionBatch.id == uuid.UUID(batch_id))
            ).scalar_one_or_none()
            item = db.execute(
                select(IngestionItem).where(IngestionItem.id == uuid.UUID(item_id))
            ).scalar_one_or_none()

            if item and item.status != IngestionItemStatus.FAILED:
                item.status = IngestionItemStatus.FAILED
                item.error_message = str(e)
                item.completed_at = datetime.utcnow()

            if batch and batch.status != IngestionBatchStatus.FAILED:
                batch.status = IngestionBatchStatus.FAILED
                batch.failed_items = 1
                batch.processed_items = 1
                batch.completed_at = datetime.utcnow()

            db.commit()
        except Exception:
            pass

        raise
    finally:
        db.close()


def _attach_to_project(
    db: Session,
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: str | None,
) -> None:
    """Attach a document to a project if not already attached."""
    from evidence_repository.models.project import ProjectDocument

    # Check if already attached
    existing = db.execute(
        select(ProjectDocument).where(
            ProjectDocument.project_id == project_id,
            ProjectDocument.document_id == document_id,
        )
    ).scalar_one_or_none()

    if not existing:
        project_doc = ProjectDocument(
            project_id=project_id,
            document_id=document_id,
            attached_by=user_id,
        )
        db.add(project_doc)
        db.flush()


# =============================================================================
# Structured Extraction Tasks
# =============================================================================


def task_extract_structured(
    document_id: str,
    project_id: str,
    version_id: str | None = None,
    reprocess: bool = False,
) -> dict:
    """Extract structured metrics and claims from a document.

    Uses LLM-based extraction to identify Juris-critical facts:
    - Metrics: ARR, Revenue, Burn, Runway, Cash, Headcount, Churn, NRR
    - Claims: SOC2, ISO27001, GDPR, IP ownership, security incidents

    All extractions reference source span_ids for traceability.

    Args:
        document_id: Document ID to extract from.
        project_id: Project to associate extractions with.
        version_id: Optional specific version (defaults to latest).
        reprocess: If True, delete existing extractions first.

    Returns:
        Dict with extraction results.
    """
    _update_progress(0, "Starting structured extraction")

    from evidence_repository.extraction.structured_extraction import (
        StructuredExtractionService,
    )
    from evidence_repository.models.evidence import Span

    db = _get_sync_db_session()

    try:
        doc_uuid = uuid.UUID(document_id)
        proj_uuid = uuid.UUID(project_id)

        # Get document version
        if version_id:
            version = db.execute(
                select(DocumentVersion).where(DocumentVersion.id == uuid.UUID(version_id))
            ).scalar_one_or_none()
        else:
            version = db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc_uuid)
                .order_by(DocumentVersion.version_number.desc())
            ).scalars().first()

        if not version:
            raise ValueError(f"No version found for document {document_id}")

        _update_progress(10, "Found document version")

        # Check for spans
        spans_count = db.execute(
            select(Span.id).where(Span.document_version_id == version.id)
        ).fetchall()

        if not spans_count:
            return {
                "document_id": document_id,
                "project_id": project_id,
                "version_id": str(version.id),
                "status": "no_spans",
                "message": "No spans found for extraction. Run span generation first.",
            }

        _update_progress(20, f"Found {len(spans_count)} spans to process")

        # Run extraction synchronously
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        settings = get_settings()

        async def run_extraction():
            engine = create_async_engine(settings.database_url)
            async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with async_session() as session:
                service = StructuredExtractionService(db=session)
                stats = await service.extract_from_version(
                    version_id=version.id,
                    project_id=proj_uuid,
                    reprocess=reprocess,
                )
                await session.commit()
                return stats

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            stats = loop.run_until_complete(run_extraction())
        finally:
            loop.close()

        _update_progress(100, "Structured extraction complete")

        return {
            "document_id": document_id,
            "project_id": project_id,
            "version_id": str(version.id),
            "status": "completed",
            "spans_processed": stats.spans_processed,
            "metrics_extracted": stats.metrics_extracted,
            "claims_extracted": stats.claims_extracted,
            "errors": stats.errors,
        }

    except Exception as e:
        logger.error(f"Structured extraction failed for {document_id}: {e}")
        raise
    finally:
        db.close()


def task_extract_structured_batch(
    document_ids: list[str],
    project_id: str,
    reprocess: bool = False,
) -> dict:
    """Extract structured data from multiple documents.

    Args:
        document_ids: List of document IDs.
        project_id: Project to associate extractions with.
        reprocess: If True, delete existing extractions first.

    Returns:
        Dict with batch extraction results.
    """
    _update_progress(0, f"Starting batch extraction for {len(document_ids)} documents")

    results = []
    total = len(document_ids)

    for i, doc_id in enumerate(document_ids):
        progress = (i / total) * 100
        _update_progress(progress, f"Processing document {i + 1}/{total}")

        try:
            result = task_extract_structured(
                document_id=doc_id,
                project_id=project_id,
                reprocess=reprocess,
            )
            results.append({
                "document_id": doc_id,
                "status": "success",
                "result": result,
            })
        except Exception as e:
            logger.error(f"Extraction failed for {doc_id}: {e}")
            results.append({
                "document_id": doc_id,
                "status": "error",
                "error": str(e),
            })

    _update_progress(100, "Batch extraction complete")

    successful = len([r for r in results if r["status"] == "success"])
    failed = len([r for r in results if r["status"] == "error"])

    total_metrics = sum(
        r["result"]["metrics_extracted"]
        for r in results
        if r["status"] == "success" and "metrics_extracted" in r.get("result", {})
    )
    total_claims = sum(
        r["result"]["claims_extracted"]
        for r in results
        if r["status"] == "success" and "claims_extracted" in r.get("result", {})
    )

    return {
        "project_id": project_id,
        "documents_processed": total,
        "successful": successful,
        "failed": failed,
        "total_metrics_extracted": total_metrics,
        "total_claims_extracted": total_claims,
        "results": results,
    }


# =============================================================================
# Multi-Level Extraction Tasks
# =============================================================================


def task_multilevel_extract(
    version_id: str,
    profile_code: str = "general",
    process_context: str = "unspecified",
    level: int = 2,
    triggered_by: str | None = None,
    compute_missing_levels: bool = False,
    schema_version: str = "1.0",
    vocab_version: str = "1.0",
) -> dict:
    """Run multi-level extraction for a document version.

    Extracts facts (claims, metrics, constraints, risks) at the specified
    level of detail using domain-specific vocabularies and process context.

    Args:
        version_id: Document version ID.
        profile_code: Extraction profile (general, vc, pharma, insurance).
        process_context: Business process context (e.g., vc.ic_decision).
        level: Extraction level (1=basic, 2=standard, 3=deep, 4=forensic).
        triggered_by: User who triggered the extraction.
        compute_missing_levels: If True, compute all lower levels first.
        schema_version: Schema version for output reproducibility.
        vocab_version: Vocabulary version used.

    Returns:
        Dict with extraction run results.
    """
    _update_progress(0, f"Starting L{level} {profile_code}/{process_context} extraction")

    settings = get_settings()

    try:
        ver_uuid = uuid.UUID(version_id)

        # Run async extraction in sync context
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        async def run_extraction():
            from evidence_repository.extraction.multilevel import MultiLevelExtractionService

            engine = create_async_engine(settings.database_url)
            async_session_maker = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            results = []

            async with async_session_maker() as session:
                service = MultiLevelExtractionService()

                # If compute_missing_levels, run all levels up to requested
                if compute_missing_levels and level > 1:
                    for lvl in range(1, level):
                        progress = ((lvl - 1) / level) * 80
                        _update_progress(progress, f"Computing L{lvl} extraction")

                        try:
                            run = await service.extract(
                                session=session,
                                version_id=ver_uuid,
                                profile_code=profile_code,
                                process_context=process_context,
                                level=lvl,
                                triggered_by=triggered_by,
                                schema_version=schema_version,
                                vocab_version=vocab_version,
                            )
                            results.append({
                                "level": lvl,
                                "run_id": str(run.id),
                                "status": run.status.value,
                                "process_context": process_context,
                            })
                        except Exception as e:
                            logger.warning(f"L{lvl} extraction failed: {e}")
                            results.append({
                                "level": lvl,
                                "status": "failed",
                                "error": str(e),
                            })

                # Run requested level
                _update_progress(80, f"Computing L{level} extraction")
                run = await service.extract(
                    session=session,
                    version_id=ver_uuid,
                    profile_code=profile_code,
                    process_context=process_context,
                    level=level,
                    triggered_by=triggered_by,
                    schema_version=schema_version,
                    vocab_version=vocab_version,
                )

                results.append({
                    "level": level,
                    "run_id": str(run.id),
                    "status": run.status.value,
                    "process_context": process_context,
                    "metadata": run.metadata_,
                })

                return {
                    "version_id": version_id,
                    "profile_code": profile_code,
                    "process_context": process_context,
                    "requested_level": level,
                    "schema_version": schema_version,
                    "vocab_version": vocab_version,
                    "runs": results,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(run_extraction())
        finally:
            loop.close()

        _update_progress(100, "Multi-level extraction complete")
        return result

    except Exception as e:
        logger.error(f"Multi-level extraction failed for {version_id}: {e}")
        raise


def task_multilevel_extract_batch(
    version_ids: list[str],
    profile_code: str = "general",
    process_context: str = "unspecified",
    level: int = 2,
    triggered_by: str | None = None,
    schema_version: str = "1.0",
    vocab_version: str = "1.0",
) -> dict:
    """Run multi-level extraction for multiple document versions.

    Args:
        version_ids: List of document version IDs.
        profile_code: Extraction profile.
        process_context: Business process context.
        level: Extraction level.
        triggered_by: User who triggered the extraction.
        schema_version: Schema version for output.
        vocab_version: Vocabulary version used.

    Returns:
        Dict with batch results.
    """
    _update_progress(0, f"Starting batch L{level} {process_context} extraction for {len(version_ids)} versions")

    results = []
    total = len(version_ids)

    for i, ver_id in enumerate(version_ids):
        progress = (i / total) * 100
        _update_progress(progress, f"Processing version {i + 1}/{total}")

        try:
            result = task_multilevel_extract(
                version_id=ver_id,
                profile_code=profile_code,
                process_context=process_context,
                level=level,
                triggered_by=triggered_by,
                compute_missing_levels=False,
                schema_version=schema_version,
                vocab_version=vocab_version,
            )
            results.append({
                "version_id": ver_id,
                "status": "success",
                "result": result,
            })
        except Exception as e:
            logger.error(f"Extraction failed for {ver_id}: {e}")
            results.append({
                "version_id": ver_id,
                "status": "error",
                "error": str(e),
            })

    _update_progress(100, "Batch extraction complete")

    successful = len([r for r in results if r["status"] == "success"])
    failed = len([r for r in results if r["status"] == "error"])

    return {
        "profile_code": profile_code,
        "process_context": process_context,
        "level": level,
        "versions_processed": total,
        "successful": successful,
        "failed": failed,
        "results": results,
    }


# =============================================================================
# Document Version Processing Pipeline (Idempotent)
# =============================================================================


class PipelineStep:
    """Enumeration of pipeline steps with progress weights."""

    EXTRACT = ("extract", 0, 20)
    BUILD_SPANS = ("build_spans", 20, 40)
    BUILD_EMBEDDINGS = ("build_embeddings", 40, 60)
    EXTRACT_FACTS = ("extract_facts", 60, 80)
    QUALITY_CHECK = ("quality_check", 80, 100)


def task_process_document_version(
    version_id: str,
    project_id: str | None = None,
    profile_code: str = "general",
    process_context: str = "unspecified",
    extraction_level: int = 2,
    skip_extraction: bool = False,
    skip_spans: bool = False,
    skip_embeddings: bool = False,
    skip_facts: bool = False,
    skip_quality: bool = False,
    reprocess: bool = False,
) -> dict:
    """Process a document version through the complete pipeline.

    This is the main idempotent pipeline for processing document versions.
    Each step checks for existing results and skips if already completed
    (unless reprocess=True).

    Pipeline Steps:
    1. Extract (format-specific text extraction)
    2. Build spans (create evidence spans from extracted text)
    3. Build embeddings (generate vector embeddings for spans)
    4. Extract facts (extract metrics and claims using LLM)
    5. Quality checks (detect conflicts and open questions)

    Args:
        version_id: Document version ID to process.
        project_id: Optional project ID for fact association.
        profile_code: Extraction profile (general, vc, pharma, insurance).
        process_context: Business process context (e.g., vc.ic_decision).
        extraction_level: Level of detail for fact extraction (1-4).
        skip_extraction: Skip text extraction step.
        skip_spans: Skip span building step.
        skip_embeddings: Skip embedding generation step.
        skip_facts: Skip fact extraction step.
        skip_quality: Skip quality analysis step.
        reprocess: If True, reprocess even if already completed.

    Returns:
        Dict with results from each pipeline step.
    """
    _update_progress(0, "Starting document version pipeline")

    db = _get_sync_db_session()
    storage = _get_storage()
    settings = get_settings()

    result = {
        "version_id": version_id,
        "project_id": project_id,
        "profile_code": profile_code,
        "process_context": process_context,
        "extraction_level": extraction_level,
        "steps_completed": [],
        "steps_skipped": [],
        "errors": [],
    }

    try:
        # Load document version
        ver_uuid = uuid.UUID(version_id)
        version = db.execute(
            select(DocumentVersion).where(DocumentVersion.id == ver_uuid)
        ).scalar_one_or_none()

        if not version:
            raise ValueError(f"Document version {version_id} not found")

        document = db.execute(
            select(Document).where(Document.id == version.document_id)
        ).scalar_one_or_none()

        if not document:
            raise ValueError(f"Document {version.document_id} not found")

        result["document_id"] = str(version.document_id)
        result["filename"] = document.filename

        # =====================================================================
        # Step 1: Extract (format-specific text extraction)
        # =====================================================================
        if not skip_extraction:
            step_result = _pipeline_step_extract(
                db, storage, version, document, reprocess
            )
            result["extract"] = step_result
            if step_result.get("status") == "completed":
                result["steps_completed"].append("extract")
            elif step_result.get("status") == "skipped":
                result["steps_skipped"].append("extract")
            else:
                result["errors"].append(f"extract: {step_result.get('error')}")
        else:
            result["steps_skipped"].append("extract")

        _update_progress(20, "Step 1/5: Extraction complete")

        # =====================================================================
        # Step 2: Build spans
        # =====================================================================
        if not skip_spans:
            step_result = _pipeline_step_build_spans(db, version, reprocess)
            result["build_spans"] = step_result
            if step_result.get("status") == "completed":
                result["steps_completed"].append("build_spans")
            elif step_result.get("status") == "skipped":
                result["steps_skipped"].append("build_spans")
            else:
                result["errors"].append(f"build_spans: {step_result.get('error')}")
        else:
            result["steps_skipped"].append("build_spans")

        _update_progress(40, "Step 2/5: Span building complete")

        # =====================================================================
        # Step 3: Build embeddings
        # =====================================================================
        if not skip_embeddings:
            step_result = _pipeline_step_build_embeddings(db, version, reprocess)
            result["build_embeddings"] = step_result
            if step_result.get("status") == "completed":
                result["steps_completed"].append("build_embeddings")
            elif step_result.get("status") == "skipped":
                result["steps_skipped"].append("build_embeddings")
            else:
                result["errors"].append(f"build_embeddings: {step_result.get('error')}")
        else:
            result["steps_skipped"].append("build_embeddings")

        _update_progress(60, "Step 3/5: Embeddings complete")

        # =====================================================================
        # Step 4: Extract facts
        # =====================================================================
        if not skip_facts and project_id:
            step_result = _pipeline_step_extract_facts(
                db, version, project_id, profile_code, process_context, extraction_level, reprocess
            )
            result["extract_facts"] = step_result
            if step_result.get("status") == "completed":
                result["steps_completed"].append("extract_facts")
            elif step_result.get("status") == "skipped":
                result["steps_skipped"].append("extract_facts")
            else:
                result["errors"].append(f"extract_facts: {step_result.get('error')}")
        else:
            result["steps_skipped"].append("extract_facts")
            if not project_id and not skip_facts:
                result["extract_facts"] = {"status": "skipped", "reason": "no_project_id"}

        _update_progress(80, "Step 4/5: Fact extraction complete")

        # =====================================================================
        # Step 5: Quality checks
        # =====================================================================
        if not skip_quality and project_id:
            step_result = _pipeline_step_quality_check(
                db, version, project_id, profile_code, extraction_level
            )
            result["quality_check"] = step_result
            if step_result.get("status") == "completed":
                result["steps_completed"].append("quality_check")
            elif step_result.get("status") == "skipped":
                result["steps_skipped"].append("quality_check")
            else:
                result["errors"].append(f"quality_check: {step_result.get('error')}")
        else:
            result["steps_skipped"].append("quality_check")

        _update_progress(100, "Pipeline complete")

        result["status"] = "completed" if not result["errors"] else "partial"
        return result

    except Exception as e:
        logger.error(f"Pipeline failed for version {version_id}: {e}")
        result["status"] = "failed"
        result["error"] = str(e)
        raise
    finally:
        db.close()


def _pipeline_step_extract(
    db: Session,
    storage: StorageBackend,
    version,
    document,
    reprocess: bool,
) -> dict:
    """Step 1: Extract text from document.

    Idempotent: Skips if extraction_status is COMPLETED and reprocess=False.
    """
    from evidence_repository.models.document import ExtractionStatus

    # Check if already extracted
    if (
        version.extraction_status == ExtractionStatus.COMPLETED
        and version.extracted_text
        and not reprocess
    ):
        return {
            "status": "skipped",
            "reason": "already_extracted",
            "text_length": len(version.extracted_text),
        }

    try:
        # Update status
        version.extraction_status = ExtractionStatus.PROCESSING
        db.flush()

        # Download file content
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            file_data = loop.run_until_complete(storage.download(version.storage_path))
        finally:
            loop.close()

        # Extract based on content type
        text = ""
        page_count = None

        if document.content_type == "application/pdf":
            text, page_count = _extract_pdf_text(file_data)
        elif document.content_type in ["text/plain", "text/markdown", "text/csv"]:
            text = _extract_text_content(file_data)
        elif document.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            text = _extract_xlsx_text(file_data)
        elif document.content_type.startswith("image/"):
            text = _extract_image_text(file_data, document.content_type)
        else:
            raise ValueError(f"Unsupported content type: {document.content_type}")

        # Update version
        version.extracted_text = text
        version.extraction_status = ExtractionStatus.COMPLETED
        _set_processing_status(version, ProcessingStatus.EXTRACTED)
        version.extracted_at = datetime.utcnow()
        version.page_count = page_count
        version.extraction_error = None
        db.commit()

        return {
            "status": "completed",
            "text_length": len(text),
            "page_count": page_count,
        }

    except Exception as e:
        version.extraction_status = ExtractionStatus.FAILED
        _set_processing_status(version, ProcessingStatus.FAILED)
        version.extraction_error = str(e)
        db.commit()
        return {"status": "error", "error": str(e)}


def _pipeline_step_build_spans(
    db: Session,
    version,
    reprocess: bool,
) -> dict:
    """Step 2: Build spans from extracted text.

    Idempotent: Skips if spans already exist and reprocess=False.
    """
    from evidence_repository.models.evidence import Span, SpanType

    # Check if spans already exist
    existing_spans = db.execute(
        select(Span).where(Span.document_version_id == version.id).limit(1)
    ).scalar_one_or_none()

    if existing_spans and not reprocess:
        # Count existing spans
        span_count = db.execute(
            select(Span.id).where(Span.document_version_id == version.id)
        ).fetchall()
        return {
            "status": "skipped",
            "reason": "spans_exist",
            "span_count": len(span_count),
        }

    try:
        # Delete existing spans if reprocessing
        if reprocess:
            db.execute(
                Span.__table__.delete().where(Span.document_version_id == version.id)
            )
            db.flush()

        # Check if we have extracted text
        if not version.extracted_text:
            return {"status": "skipped", "reason": "no_extracted_text"}

        # Build spans from text - simple paragraph-based chunking
        spans_created = _build_spans_from_text(db, version)

        # Update processing status
        _set_processing_status(version, ProcessingStatus.SPANS_BUILT)
        db.commit()

        return {
            "status": "completed",
            "spans_created": spans_created,
        }

    except Exception as e:
        db.rollback()
        _set_processing_status(version, ProcessingStatus.FAILED)
        db.commit()
        return {"status": "error", "error": str(e)}


def _build_spans_from_text(db: Session, version) -> int:
    """Build spans from extracted text using paragraph-based chunking."""
    import hashlib
    import re
    from evidence_repository.models.evidence import Span, SpanType

    text = version.extracted_text
    if not text:
        return 0

    # Split by double newlines or page markers
    parts = re.split(r'\n\n+|\f', text)

    spans_created = 0
    current_pos = 0

    for i, part in enumerate(parts):
        part = part.strip()
        if not part or len(part) < 10:  # Skip very short paragraphs
            current_pos += len(part) + 2
            continue

        # Compute span hash for idempotency
        span_hash = hashlib.sha256(
            f"{version.id}:{i}:{part[:100]}".encode()
        ).hexdigest()[:64]

        # Check if span with this hash already exists
        existing = db.execute(
            select(Span).where(
                Span.document_version_id == version.id,
                Span.span_hash == span_hash,
            )
        ).scalar_one_or_none()

        if existing:
            current_pos += len(part) + 2
            continue

        # Determine span type based on content
        span_type = SpanType.TEXT
        if re.match(r'^#+\s|^[A-Z][A-Z\s]{2,}$', part):
            span_type = SpanType.HEADING
        elif '|' in part and part.count('|') > 2:
            span_type = SpanType.TABLE

        # Create span
        span = Span(
            document_version_id=version.id,
            span_hash=span_hash,
            start_locator={
                "type": "text",
                "char_offset_start": current_pos,
                "char_offset_end": current_pos + len(part),
                "paragraph_index": i,
            },
            end_locator=None,
            text_content=part,
            span_type=span_type,
            metadata_={"paragraph_index": i},
        )
        db.add(span)
        spans_created += 1
        current_pos += len(part) + 2

    return spans_created


def _pipeline_step_build_embeddings(
    db: Session,
    version,
    reprocess: bool,
) -> dict:
    """Step 3: Generate embeddings for spans.

    Idempotent: Skips spans that already have embeddings (unless reprocess=True).
    """
    from evidence_repository.embeddings.openai_client import OpenAIEmbeddingClient
    from evidence_repository.models.embedding import EmbeddingChunk
    from evidence_repository.models.evidence import Span, SpanType

    # Embeddable span types (text-based spans only)
    EMBEDDABLE_SPAN_TYPES = {SpanType.TEXT, SpanType.HEADING, SpanType.CITATION, SpanType.FOOTNOTE}

    try:
        # Get spans that need embeddings
        spans = db.execute(
            select(Span)
            .where(
                Span.document_version_id == version.id,
                Span.span_type.in_(EMBEDDABLE_SPAN_TYPES),
            )
            .order_by(Span.created_at)
        ).scalars().all()

        if not spans:
            return {"status": "skipped", "reason": "no_embeddable_spans"}

        # Check which spans already have embeddings
        spans_to_embed = []
        if not reprocess:
            span_ids = [s.id for s in spans]
            existing_embeddings = db.execute(
                select(EmbeddingChunk.span_id)
                .where(EmbeddingChunk.span_id.in_(span_ids))
            ).fetchall()
            existing_ids = {row[0] for row in existing_embeddings}

            spans_to_embed = [s for s in spans if s.id not in existing_ids]
        else:
            # Delete existing embeddings for this version
            db.execute(
                EmbeddingChunk.__table__.delete().where(
                    EmbeddingChunk.document_version_id == version.id
                )
            )
            db.flush()
            spans_to_embed = list(spans)

        if not spans_to_embed:
            return {
                "status": "skipped",
                "reason": "all_spans_have_embeddings",
                "total_spans": len(spans),
            }

        # Filter out empty spans
        valid_spans = [s for s in spans_to_embed if s.text_content and s.text_content.strip()]
        if not valid_spans:
            return {"status": "skipped", "reason": "no_valid_span_content"}

        # Generate embeddings in batches
        client = OpenAIEmbeddingClient()
        BATCH_SIZE = 50

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        chunks_created = 0
        try:
            for batch_start in range(0, len(valid_spans), BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, len(valid_spans))
                batch_spans = valid_spans[batch_start:batch_end]

                texts = [s.text_content for s in batch_spans]
                embeddings = loop.run_until_complete(client.embed_texts(texts))

                for span, embedding, idx in zip(batch_spans, embeddings, range(len(batch_spans))):
                    chunk = EmbeddingChunk(
                        document_version_id=version.id,
                        span_id=span.id,
                        chunk_index=idx,
                        text=span.text_content,
                        embedding=embedding,
                        metadata_={
                            "span_type": span.span_type.value,
                            "span_hash": span.span_hash,
                        },
                    )
                    db.add(chunk)
                    chunks_created += 1
        finally:
            loop.close()

        # Update processing status
        _set_processing_status(version, ProcessingStatus.EMBEDDED)
        db.commit()

        return {
            "status": "completed",
            "spans_embedded": chunks_created,
            "spans_skipped": len(spans) - len(valid_spans),
            "tokens_used": client.get_token_usage(),
        }

    except Exception as e:
        db.rollback()
        _set_processing_status(version, ProcessingStatus.FAILED)
        db.commit()
        return {"status": "error", "error": str(e)}


def _pipeline_step_extract_facts(
    db: Session,
    version,
    project_id: str,
    profile_code: str,
    process_context: str,
    extraction_level: int,
    reprocess: bool,
) -> dict:
    """Step 4: Extract facts (metrics and claims) from spans.

    Idempotent: Checks for existing extraction runs for the given
    (version, profile, process_context, level) tuple.
    """
    try:
        settings = get_settings()

        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker as async_sessionmaker

        async def run_extraction():
            from evidence_repository.extraction.multilevel import MultiLevelExtractionService
            from evidence_repository.models.extraction_level import (
                ExtractionProfile,
                ExtractionProfileCode,
                ExtractionRunStatus,
                FactExtractionRun,
                ProcessContext,
            )

            engine = create_async_engine(settings.database_url)
            async_session_maker = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            # Parse process context
            try:
                process_ctx = ProcessContext(process_context)
            except ValueError:
                process_ctx = ProcessContext.UNSPECIFIED

            async with async_session_maker() as session:
                service = MultiLevelExtractionService()

                # Check if extraction already exists
                if not reprocess:
                    try:
                        code_enum = ExtractionProfileCode(profile_code)
                    except ValueError:
                        code_enum = ExtractionProfileCode.GENERAL

                    # Get profile
                    profile_stmt = select(ExtractionProfile).where(
                        ExtractionProfile.code == code_enum
                    )
                    profile_result = await session.execute(profile_stmt)
                    profile = profile_result.scalar_one_or_none()

                    if profile:
                        # Check for existing successful run with same process_context
                        existing_stmt = select(FactExtractionRun).where(
                            FactExtractionRun.version_id == version.id,
                            FactExtractionRun.profile_id == profile.id,
                            FactExtractionRun.process_context == process_ctx,
                            FactExtractionRun.status == ExtractionRunStatus.SUCCEEDED,
                        )
                        existing_result = await session.execute(existing_stmt)
                        existing_run = existing_result.scalar_one_or_none()

                        if existing_run:
                            return {
                                "status": "skipped",
                                "reason": "extraction_exists",
                                "existing_run_id": str(existing_run.id),
                                "process_context": process_context,
                            }

                # Run extraction
                run = await service.extract(
                    session=session,
                    version_id=version.id,
                    profile_code=profile_code,
                    process_context=process_context,
                    level=extraction_level,
                    triggered_by="pipeline",
                )

                return {
                    "status": "completed",
                    "run_id": str(run.id),
                    "run_status": run.status.value,
                    "process_context": process_context,
                    "metadata": run.metadata_,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_extraction())
        finally:
            loop.close()

        # Update processing status on success
        if result.get("status") == "completed":
            _set_processing_status(version, ProcessingStatus.FACTS_EXTRACTED)
            db.commit()

        return result

    except Exception as e:
        _set_processing_status(version, ProcessingStatus.FAILED)
        db.commit()
        return {"status": "error", "error": str(e)}


def _pipeline_step_quality_check(
    db: Session,
    version,
    project_id: str,
    profile_code: str,
    extraction_level: int,
) -> dict:
    """Step 5: Run quality analysis on extracted facts.

    This step is always run (not idempotent) as it provides current analysis.
    """
    try:
        settings = get_settings()

        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker as async_sessionmaker

        async def run_quality_check():
            from evidence_repository.services.quality_analysis import QualityAnalysisService

            engine = create_async_engine(settings.database_url)
            async_session_maker = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            async with async_session_maker() as session:
                service = QualityAnalysisService(db=session)

                result = await service.analyze_document(
                    document_id=version.document_id,
                    version_id=version.id,
                )

                return {
                    "status": "completed",
                    "metric_conflicts": len(result.metric_conflicts),
                    "claim_conflicts": len(result.claim_conflicts),
                    "open_questions": len(result.open_questions),
                    "summary": result.summary,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_quality_check())
        finally:
            loop.close()

        # Update processing status on success
        if result.get("status") == "completed":
            _set_processing_status(version, ProcessingStatus.QUALITY_CHECKED)
            db.commit()

        return result

    except Exception as e:
        _set_processing_status(version, ProcessingStatus.FAILED)
        db.commit()
        return {"status": "error", "error": str(e)}


def task_upgrade_extraction_level(
    version_id: str,
    profile_code: str,
    process_context: str = "unspecified",
    target_level: int = 2,
    triggered_by: str | None = None,
    schema_version: str = "1.0",
    vocab_version: str = "1.0",
) -> dict:
    """Upgrade extraction to a higher level.

    Computes all missing levels up to the target level for the given
    (profile, process_context) combination. Never overwrites existing
    extraction results.

    Args:
        version_id: Document version ID.
        profile_code: Extraction profile.
        process_context: Business process context (e.g., vc.ic_decision).
        target_level: Target extraction level (1-4).
        triggered_by: User who triggered the upgrade.
        schema_version: Schema version for output.
        vocab_version: Vocabulary version used.

    Returns:
        Dict with upgrade results.
    """
    _update_progress(0, f"Upgrading to L{target_level} {process_context} extraction")

    settings = get_settings()

    try:
        ver_uuid = uuid.UUID(version_id)

        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select

        async def run_upgrade():
            from evidence_repository.extraction.multilevel import MultiLevelExtractionService
            from evidence_repository.models.extraction_level import (
                ExtractionProfile,
                ExtractionProfileCode,
                ExtractionRunStatus,
                FactExtractionRun,
                ProcessContext,
            )

            engine = create_async_engine(settings.database_url)
            async_session_maker = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )

            # Parse process context
            try:
                process_ctx = ProcessContext(process_context)
            except ValueError:
                process_ctx = ProcessContext.UNSPECIFIED

            async with async_session_maker() as session:
                service = MultiLevelExtractionService()

                # Get profile
                try:
                    code_enum = ExtractionProfileCode(profile_code)
                except ValueError:
                    code_enum = ExtractionProfileCode.GENERAL

                profile_stmt = select(ExtractionProfile).where(
                    ExtractionProfile.code == code_enum
                )
                profile_result = await session.execute(profile_stmt)
                profile = profile_result.scalar_one_or_none()

                if not profile:
                    # Create profile on first use
                    profile = await service._get_or_create_profile(session, profile_code)

                # Check which levels already exist for this (profile, process_context)
                existing_runs_stmt = select(FactExtractionRun).where(
                    FactExtractionRun.version_id == ver_uuid,
                    FactExtractionRun.profile_id == profile.id,
                    FactExtractionRun.process_context == process_ctx,
                    FactExtractionRun.status == ExtractionRunStatus.SUCCEEDED,
                )
                existing_result = await session.execute(existing_runs_stmt)
                existing_runs = existing_result.scalars().all()

                # Get existing level ranks
                existing_levels = set()
                for run in existing_runs:
                    level_record = await session.get(
                        "ExtractionLevel", run.level_id
                    )
                    if level_record:
                        existing_levels.add(level_record.rank)

                # Compute missing levels
                missing_levels = [
                    lvl for lvl in range(1, target_level + 1)
                    if lvl not in existing_levels
                ]

                if not missing_levels:
                    return {
                        "version_id": version_id,
                        "profile_code": profile_code,
                        "process_context": process_context,
                        "target_level": target_level,
                        "status": "already_complete",
                        "existing_levels": list(existing_levels),
                        "computed_levels": [],
                    }

                computed = []
                for i, lvl in enumerate(missing_levels):
                    progress = (i / len(missing_levels)) * 90
                    _update_progress(progress, f"Computing L{lvl}")

                    try:
                        run = await service.extract(
                            session=session,
                            version_id=ver_uuid,
                            profile_code=profile_code,
                            process_context=process_context,
                            level=lvl,
                            triggered_by=triggered_by,
                            schema_version=schema_version,
                            vocab_version=vocab_version,
                        )
                        computed.append({
                            "level": lvl,
                            "run_id": str(run.id),
                            "status": run.status.value,
                            "process_context": process_context,
                        })
                    except Exception as e:
                        logger.error(f"L{lvl} extraction failed: {e}")
                        computed.append({
                            "level": lvl,
                            "status": "failed",
                            "error": str(e),
                        })

                return {
                    "version_id": version_id,
                    "profile_code": profile_code,
                    "process_context": process_context,
                    "target_level": target_level,
                    "status": "upgraded",
                    "existing_levels": list(existing_levels),
                    "computed_levels": computed,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(run_upgrade())
        finally:
            loop.close()

        _update_progress(100, "Level upgrade complete")
        return result

    except Exception as e:
        logger.error(f"Level upgrade failed for {version_id}: {e}")
        raise
