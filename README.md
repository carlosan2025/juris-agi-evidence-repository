# Evidence Repository

API-first document management system designed to feed **Juris-AGI**.

## Overview

The Evidence Repository provides a robust backend for managing legal documents, extracting evidence, and supporting AI-powered legal analysis.

### Key Features

- **Global Documents**: Documents are standalone assets that can be attached to multiple projects
- **Version Control**: Every document maintains immutable versions for stable citations
- **Evidence Spans**: Precise locators (page/bbox for PDFs, sheet/cell for spreadsheets, char offsets for text)
- **Semantic Search**: Vector similarity search powered by pgvector and OpenAI embeddings
- **Evidence Packs**: Bundle evidence items for export and presentation
- **Audit Logging**: Comprehensive audit trail for all operations

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
├─────────────────────────────────────────────────────────────────┤
│  API Routes: documents, projects, search, evidence, jobs         │
├─────────────────────────────────────────────────────────────────┤
│  Services: document, project, search, evidence                   │
├─────────────────────────────────────────────────────────────────┤
│  Core: ingestion, extraction (LovePDF), embeddings (OpenAI)     │
├─────────────────────────────────────────────────────────────────┤
│  Storage: LocalFilesystem (now) | S3 (future)                   │
├─────────────────────────────────────────────────────────────────┤
│  Database: PostgreSQL + pgvector                                 │
├─────────────────────────────────────────────────────────────────┤
│  Job Queue: Redis + RQ Workers (SQS/ECS ready)                  │
└─────────────────────────────────────────────────────────────────┘
```

### Async Processing Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   FastAPI    │────>│    Redis     │<────│  RQ Worker   │
│   (Enqueue)  │     │   (Queue)    │     │  (Process)   │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                     ┌──────┴──────┐
                     │   Queues    │
                     ├─────────────┤
                     │ high        │ (extractions)
                     │ evidence    │ (normal jobs)
                     │ low         │ (bulk ingestion)
                     └─────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.11+ for local development

### 1. Clone and Setup

```bash
cd evidence-repository

# Copy environment template
cp .env.example .env

# Edit .env with your API keys (optional for basic testing)
# - LOVEPDF_PUBLIC_KEY / LOVEPDF_SECRET_KEY for PDF extraction
# - OPENAI_API_KEY for embeddings
```

### 2. Start with Docker Compose

```bash
# Build and start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

This starts:
- **API** at http://localhost:8000
- **PostgreSQL** with pgvector at localhost:5432
- **Redis** for job queue at localhost:6379
- **Worker** for background job processing
- **Migrations** run automatically

#### Optional: RQ Dashboard

```bash
# Start with monitoring dashboard
docker-compose --profile monitoring up -d

# Access RQ Dashboard at http://localhost:9181
```

### 3. Access the API

- **OpenAPI Docs**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redoc
- **Health Check**: http://localhost:8000/api/v1/health

### 4. Test the API

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Upload a document (use default dev API key)
curl -X POST http://localhost:8000/api/v1/documents \
  -H "X-API-Key: dev-key-12345" \
  -F "file=@/path/to/document.pdf"

# List documents
curl http://localhost:8000/api/v1/documents \
  -H "X-API-Key: dev-key-12345"

# Create a project
curl -X POST http://localhost:8000/api/v1/projects \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"name": "Case #123", "description": "Test case"}'

# Async upload (returns job_id immediately)
curl -X POST http://localhost:8000/api/v1/jobs/upload \
  -H "X-API-Key: dev-key-12345" \
  -F "file=@/path/to/document.pdf"

# Check job status
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: dev-key-12345"

# Bulk ingest from folder
curl -X POST http://localhost:8000/api/v1/jobs/ingest/folder \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/documents", "recursive": true}'

# Ingest from URL
curl -X POST http://localhost:8000/api/v1/jobs/ingest/url \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/document.pdf"}'
```

## Local Development

### Setup Python Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Start only Postgres (if developing locally)
docker-compose up postgres -d

# Run migrations
alembic upgrade head

# Start development server
uvicorn evidence_repository.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, start Redis
docker-compose up redis -d

# Start worker (in another terminal)
python -m evidence_repository.worker
```

### Project Structure

```
evidence-repository/
├── src/evidence_repository/
│   ├── api/              # FastAPI routes and middleware
│   │   ├── routes/       # Endpoint handlers
│   │   ├── dependencies.py
│   │   └── middleware.py
│   ├── db/               # Database engine and sessions
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── storage/          # File storage abstraction
│   ├── ingestion/        # Document upload handling
│   ├── extraction/       # Text extraction (LovePDF)
│   ├── embeddings/       # OpenAI embeddings + chunking
│   ├── services/         # Business logic layer
│   ├── queue/            # Redis + RQ job queue
│   │   ├── connection.py # Redis connection management
│   │   ├── jobs.py       # Job manager and status tracking
│   │   └── tasks.py      # Background worker tasks
│   ├── config.py         # Settings management
│   ├── worker.py         # RQ worker entry point
│   └── main.py           # FastAPI application
├── alembic/              # Database migrations
├── data/                 # Local file storage
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## API Endpoints

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents` | Upload document |
| GET | `/api/v1/documents` | List documents |
| GET | `/api/v1/documents/{id}` | Get document |
| GET | `/api/v1/documents/{id}/versions` | List versions |
| GET | `/api/v1/documents/{id}/versions/{vid}/download` | Download version |
| POST | `/api/v1/documents/{id}/extract` | Trigger extraction |
| DELETE | `/api/v1/documents/{id}` | Soft delete |

### Projects
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects` | List projects |
| GET | `/api/v1/projects/{id}` | Get project |
| PATCH | `/api/v1/projects/{id}` | Update project |
| DELETE | `/api/v1/projects/{id}` | Delete project |
| POST | `/api/v1/projects/{id}/documents` | Attach document |
| DELETE | `/api/v1/projects/{id}/documents/{doc_id}` | Detach document |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/search` | Semantic search |
| POST | `/api/v1/search/projects/{id}` | Search in project |

### Jobs (Async Processing)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/jobs/{id}` | Get job status |
| GET | `/api/v1/jobs` | List jobs (with filters) |
| DELETE | `/api/v1/jobs/{id}` | Cancel queued job |
| POST | `/api/v1/jobs/upload` | Async document upload |
| POST | `/api/v1/jobs/ingest/folder` | Bulk folder ingestion |
| POST | `/api/v1/jobs/ingest/url` | Ingest from URL |
| POST | `/api/v1/jobs/batch/extract` | Batch text extraction |
| POST | `/api/v1/jobs/batch/embed` | Batch embedding generation |

### Evidence
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/spans` | Create span |
| GET | `/api/v1/spans/{id}` | Get span |
| POST | `/api/v1/claims` | Create claim |
| POST | `/api/v1/metrics` | Create metric |
| POST | `/api/v1/evidence-packs` | Create pack |
| GET | `/api/v1/evidence-packs/{id}` | Get pack |
| POST | `/api/v1/evidence-packs/{id}/items` | Add item |
| GET | `/api/v1/evidence-packs/{id}/export` | Export pack |

## Authentication

Currently uses API key authentication via `X-API-Key` header.

```bash
# Default development keys (see .env.example)
X-API-Key: dev-key-12345
X-API-Key: test-key-67890
```

JWT Bearer token support is prepared for future upgrade - see `api/dependencies.py`.

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| `LOCAL_STORAGE_PATH` | Path for local file storage | `./data/uploads` |
| `API_KEYS` | Comma-separated valid API keys | `dev-key-12345` |
| `LOVEPDF_PUBLIC_KEY` | LovePDF API public key | - |
| `LOVEPDF_SECRET_KEY` | LovePDF API secret key | - |
| `OPENAI_API_KEY` | OpenAI API key for embeddings | - |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `CHUNK_SIZE` | Text chunk size | `1000` |
| `CHUNK_OVERLAP` | Chunk overlap | `200` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `REDIS_QUEUE_NAME` | Default queue name | `evidence_jobs` |
| `REDIS_JOB_TIMEOUT` | Job timeout (seconds) | `3600` |
| `BULK_INGESTION_BATCH_SIZE` | Files per batch | `50` |
| `URL_DOWNLOAD_TIMEOUT` | URL download timeout | `300` |
| `MAX_FILE_SIZE_MB` | Max upload size (MB) | `100` |
| `SUPPORTED_EXTENSIONS` | Allowed file types | `.pdf,.txt,.md,...` |

## Domain Model

### Core Entities

- **Document**: Global asset with metadata and content hash
- **DocumentVersion**: Immutable version with storage path and extracted text
- **Project**: Evaluation context (case file) referencing documents
- **ProjectDocument**: Junction linking projects to documents

### Evidence Entities

- **Span**: Precise reference to document location with text content
- **Claim**: Extracted assertion citing a span
- **Metric**: Extracted quantitative value citing a span
- **EvidencePack**: Collection of evidence items for export

### Locator Format

Spans use JSON locators for precise citations:

```json
// PDF locator
{"type": "pdf", "page": 5, "bbox": {"x1": 100, "y1": 200, "x2": 500, "y2": 250}}

// Spreadsheet locator
{"type": "spreadsheet", "sheet": "Summary", "cell_range": "A1:D10"}

// Text locator
{"type": "text", "char_offset_start": 1000, "char_offset_end": 1500}
```

## Storage Abstraction

The storage layer supports pluggable backends:

- **LocalFilesystemStorage** (current): Files stored in `data/uploads/`
- **S3Storage** (stubbed): Ready for AWS S3 migration

To migrate to S3:
1. Set `STORAGE_BACKEND=s3`
2. Configure AWS credentials
3. Implement the stubbed methods in `storage/s3.py`

## Async Processing

All document processing is handled asynchronously via Redis + RQ workers. This design enables:

- **Non-blocking uploads**: API returns immediately with a `job_id`
- **Progress tracking**: Poll job status via `/api/v1/jobs/{job_id}`
- **Scalable workers**: Run multiple workers for parallel processing
- **AWS-ready**: Architecture mirrors SQS/ECS for easy migration

### Job Types

| Job Type | Description | Queue |
|----------|-------------|-------|
| `document_ingest` | Process uploaded document | normal |
| `document_extract` | Extract text from document | high |
| `document_embed` | Generate embeddings | normal |
| `document_process_full` | Full pipeline (ingest → extract → embed) | normal |
| `bulk_folder_ingest` | Scan and ingest folder contents | low |
| `bulk_url_ingest` | Download and ingest from URL | normal |

### Job Status Flow

```
QUEUED → STARTED → FINISHED
                 ↘ FAILED
```

### Scaling Workers

```bash
# Run multiple workers for parallel processing
docker-compose up -d --scale worker=3

# Or manually start workers with specific queues
python -m evidence_repository.worker --queues high evidence
python -m evidence_repository.worker --queues low
```

## Supported File Types

| Extension | Type | Processing |
|-----------|------|------------|
| `.pdf` | Document | LovePDF text extraction |
| `.txt`, `.md` | Text | Direct text read |
| `.csv` | Data | CSV to text conversion |
| `.xlsx` | Spreadsheet | Sheet/cell extraction |
| `.png`, `.jpg`, `.jpeg`, `.webp` | Image | OCR placeholder (future) |

## Audit Logging

All significant operations are logged to the `audit_logs` table:

- Document upload/download/delete
- Project CRUD operations
- Document attach/detach
- Extraction runs
- Search queries
- Evidence pack operations

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
pytest

# Run specific test file
pytest tests/test_documents.py -v
```

## Troubleshooting

### Database Connection Issues

```bash
# Check Postgres is running
docker-compose ps

# View logs
docker-compose logs postgres

# Manually test connection
docker-compose exec postgres psql -U evidence -d evidence_repository
```

### Migration Issues

```bash
# Check migration status
alembic current

# View migration history
alembic history

# Reset database (development only!)
docker-compose down -v
docker-compose up -d postgres
alembic upgrade head
```

### API Errors

Check the API logs:

```bash
docker-compose logs api

# Worker logs
docker-compose logs worker
```

### Redis Connection Issues

```bash
# Check Redis is running
docker-compose ps redis

# Test Redis connection
docker-compose exec redis redis-cli ping

# View queue status
docker-compose exec redis redis-cli keys "rq:*"
```

### Worker Issues

```bash
# Check worker logs
docker-compose logs worker

# Restart worker
docker-compose restart worker

# Run worker in foreground for debugging
docker-compose run --rm worker
```

## License

MIT
