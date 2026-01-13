# Evidence Repository

API-first document management system designed to feed **Juris-AGI**.

## Quick Start (Local MVP)

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.11+ for local development

### 1. Setup

```bash
# Clone the repository
cd evidence-repository

# Copy environment template
cp .env.example .env

# Edit .env with your API keys (optional for basic testing)
# Required for full functionality:
# - OPENAI_API_KEY for embeddings and fact extraction
# - LOVEPDF_PUBLIC_KEY / LOVEPDF_SECRET_KEY for PDF extraction
```

### 2. Start Services

```bash
# Build and start all services
make up-build

# Or using docker-compose directly
docker-compose up --build -d
```

This starts:
- **API** at http://localhost:8000
- **PostgreSQL + pgvector** at localhost:5432
- **Redis** for job queue at localhost:6379
- **Worker** for background processing
- **Migrations** run automatically

### 3. Verify Installation

```bash
# Check health
make health

# Or manually
curl http://localhost:8000/api/v1/health
```

### 4. Access Documentation

- **OpenAPI Docs**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redoc

---

## Example Curl Commands

### Authentication

All API requests require the `X-API-Key` header. Default development keys:

```bash
# Use this header for all requests
-H "X-API-Key: dev-key-12345"
```

### Documents

```bash
# Upload a document
curl -X POST http://localhost:8000/api/v1/documents \
  -H "X-API-Key: dev-key-12345" \
  -F "file=@/path/to/document.pdf"

# List documents
curl http://localhost:8000/api/v1/documents \
  -H "X-API-Key: dev-key-12345"

# Get document details
curl http://localhost:8000/api/v1/documents/{document_id} \
  -H "X-API-Key: dev-key-12345"

# Download document version
curl http://localhost:8000/api/v1/documents/{document_id}/versions/{version_id}/download \
  -H "X-API-Key: dev-key-12345" \
  -o downloaded_file.pdf

# Trigger text extraction
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/extract \
  -H "X-API-Key: dev-key-12345"
```

### Projects

```bash
# Create a project
curl -X POST http://localhost:8000/api/v1/projects \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Series B Due Diligence",
    "description": "Evidence collection for Series B",
    "case_ref": "DD-2024-001"
  }'

# List projects
curl http://localhost:8000/api/v1/projects \
  -H "X-API-Key: dev-key-12345"

# Attach document to project
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/documents \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{"document_id": "{document_id}"}'
```

### Search

```bash
# Semantic search across all documents
curl -X POST http://localhost:8000/api/v1/search \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "annual recurring revenue growth",
    "limit": 10,
    "similarity_threshold": 0.7
  }'

# Search within a project
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/search \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SOC2 certification",
    "keywords": ["compliance", "security"],
    "exclude_keywords": ["draft"],
    "limit": 10
  }'
```

### Evidence Packs (Juris-AGI Integration)

```bash
# Create evidence pack
curl -X POST http://localhost:8000/api/v1/projects/{project_id}/evidence-packs \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Financial Metrics Pack",
    "description": "ARR and revenue evidence for DD",
    "span_ids": [],
    "claim_ids": [],
    "metric_ids": [],
    "include_quality_analysis": true
  }'

# Get evidence pack (full Juris-AGI response)
curl http://localhost:8000/api/v1/projects/{project_id}/evidence-packs/{pack_id} \
  -H "X-API-Key: dev-key-12345"

# List evidence packs
curl http://localhost:8000/api/v1/projects/{project_id}/evidence-packs \
  -H "X-API-Key: dev-key-12345"
```

### Async Jobs

```bash
# Async document upload (returns job_id immediately)
curl -X POST http://localhost:8000/api/v1/jobs/upload \
  -H "X-API-Key: dev-key-12345" \
  -F "file=@large_document.pdf"

# Check job status
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: dev-key-12345"

# Bulk ingest from folder
curl -X POST http://localhost:8000/api/v1/jobs/ingest/folder \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_path": "/path/to/documents",
    "recursive": true,
    "auto_process": true
  }'

# Ingest from URL
curl -X POST http://localhost:8000/api/v1/jobs/ingest/url \
  -H "X-API-Key: dev-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/annual_report.pdf",
    "filename": "annual_report_2024.pdf"
  }'
```

---

## Juris-AGI Integration

Evidence Repository is the **primary data source** for Juris-AGI legal analysis.

### Evidence Pack Response Structure

The evidence pack endpoint returns all data needed by Juris-AGI:

```json
{
  "id": "uuid",
  "project_id": "uuid",
  "name": "Due Diligence Evidence Pack",

  "documents": [
    {
      "id": "uuid",
      "filename": "financial_report.pdf",
      "content_type": "application/pdf",
      "version_id": "uuid",
      "version_number": 1,
      "extraction_status": "completed"
    }
  ],

  "spans": [
    {
      "id": "uuid",
      "document_version_id": "uuid",
      "document_filename": "financial_report.pdf",
      "span_type": "text",
      "text_content": "The company reported ARR of $10M...",
      "locator": {
        "type": "pdf",
        "page": 5,
        "bbox": {"x1": 100, "y1": 200, "x2": 500, "y2": 250}
      }
    }
  ],

  "claims": [
    {
      "id": "uuid",
      "span_id": "uuid",
      "claim_text": "Company has SOC2 Type II certification",
      "claim_type": "soc2",
      "certainty": "definite",
      "reliability": "verified",
      "extraction_confidence": 0.95
    }
  ],

  "metrics": [
    {
      "id": "uuid",
      "span_id": "uuid",
      "metric_name": "ARR",
      "metric_type": "arr",
      "metric_value": "$10M",
      "numeric_value": 10000000.0,
      "unit": "USD",
      "time_scope": "FY2024",
      "certainty": "definite",
      "reliability": "official"
    }
  ],

  "conflicts": [
    {
      "conflict_type": "metric",
      "severity": "high",
      "reason": "Conflicting ARR values for same period",
      "affected_ids": ["metric-1", "metric-2"],
      "details": {
        "metric_name": "ARR",
        "values": [10000000, 8000000]
      }
    }
  ],

  "open_questions": [
    {
      "category": "missing_data",
      "question": "What currency is the revenue reported in?",
      "context": "Revenue value lacks currency specification",
      "related_ids": ["metric-3"]
    }
  ],

  "quality_summary": {
    "total_conflicts": 2,
    "critical_conflicts": 0,
    "high_conflicts": 1,
    "total_open_questions": 3
  }
}
```

### Conflict Detection

The quality analysis detects:

1. **Metric Conflicts**: Same metric + overlapping period + different values
2. **Claim Conflicts**: Same boolean claim with contradictory values

### Open Questions

Flags items needing human attention:

1. **Missing Data**: Units, currency, time periods not specified
2. **Temporal Issues**: Financial data older than 12 months
3. **Ambiguity**: Values that could be interpreted multiple ways

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://evidence:evidence_secret@localhost:5432/evidence_repository` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| `FILE_STORAGE_ROOT` | Path for local file storage | `./data/files` |
| `API_KEYS` | Comma-separated valid API keys | `dev-key-12345,test-key-67890` |
| `OPENAI_API_KEY` | OpenAI API key for embeddings | (required for embeddings) |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `LOVEPDF_PUBLIC_KEY` | LovePDF public key | (required for PDF extraction) |
| `LOVEPDF_SECRET_KEY` | LovePDF secret key | (required for PDF extraction) |
| `CHUNK_SIZE` | Text chunk size for embeddings | `1000` |
| `CHUNK_OVERLAP` | Chunk overlap | `200` |
| `REDIS_QUEUE_NAME` | Default queue name | `evidence_jobs` |
| `REDIS_JOB_TIMEOUT` | Job timeout (seconds) | `3600` |
| `MAX_FILE_SIZE_MB` | Max upload size (MB) | `100` |

---

## Make Commands

```bash
# Setup
make install        # Install Python dependencies locally
make build          # Build Docker images

# Services
make up             # Start all services
make up-build       # Build and start
make up-monitor     # Start with RQ dashboard
make down           # Stop all services
make restart        # Restart services
make logs           # View logs

# Database
make migrate        # Run migrations
make db-shell       # Open PostgreSQL shell
make db-reset       # Reset database (WARNING: destroys data)

# Testing
make test           # Run all tests
make test-unit      # Run unit tests
make test-int       # Run integration tests
make test-cov       # Run with coverage

# Development
make lint           # Run linters
make format         # Auto-format code
make dev-api        # Run API locally
make dev-worker     # Run worker locally

# Monitoring
make health         # Check service health
make queue-status   # Show job queue status
make demo           # Run quick demo
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Application                         │
├─────────────────────────────────────────────────────────────────┤
│  API Routes: documents, projects, search, evidence, jobs         │
├─────────────────────────────────────────────────────────────────┤
│  Services: document, project, search, evidence, quality          │
├─────────────────────────────────────────────────────────────────┤
│  Core: ingestion, extraction (LovePDF), embeddings (OpenAI)     │
├─────────────────────────────────────────────────────────────────┤
│  Storage: LocalFilesystem (MVP) | S3 (future)                   │
├─────────────────────────────────────────────────────────────────┤
│  Database: PostgreSQL + pgvector                                 │
├─────────────────────────────────────────────────────────────────┤
│  Job Queue: Redis + RQ Workers                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Document Processing Pipeline

```
Upload → Ingest → Extract Text → Build Spans → Generate Embeddings → Extract Facts → Quality Check
         │                │              │               │                │              │
       (async)       (format-specific)   (paragraphs)   (OpenAI)      (LLM)      (conflicts)
```

Each step is **idempotent** - safe to retry without duplicating work.

---

## API Endpoints

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/documents` | Upload document |
| GET | `/api/v1/documents` | List documents |
| GET | `/api/v1/documents/{id}` | Get document |
| GET | `/api/v1/documents/{id}/versions` | List versions |
| GET | `/api/v1/documents/{id}/versions/{vid}/download` | Download |
| POST | `/api/v1/documents/{id}/extract` | Trigger extraction |
| GET | `/api/v1/documents/{id}/quality` | Get quality analysis |

### Projects
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects` | List projects |
| GET | `/api/v1/projects/{id}` | Get project |
| PATCH | `/api/v1/projects/{id}` | Update project |
| POST | `/api/v1/projects/{id}/documents` | Attach document |
| DELETE | `/api/v1/projects/{id}/documents/{doc_id}` | Detach |

### Search
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/search` | Global semantic search |
| POST | `/api/v1/projects/{id}/search` | Project-scoped search |

### Evidence Packs (Juris-AGI)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/projects/{id}/evidence-packs` | Create pack |
| GET | `/api/v1/projects/{id}/evidence-packs` | List packs |
| GET | `/api/v1/projects/{id}/evidence-packs/{pack_id}` | Get pack |

### Jobs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/jobs/{id}` | Get job status |
| GET | `/api/v1/jobs` | List jobs |
| POST | `/api/v1/jobs/upload` | Async upload |
| POST | `/api/v1/jobs/ingest/folder` | Bulk folder ingest |
| POST | `/api/v1/jobs/ingest/url` | URL ingest |

---

## Testing

```bash
# Run all tests
make test

# Run integration tests (requires running services)
make test-int

# Run with coverage
make test-cov
```

### Integration Test Coverage

The integration tests verify the complete flow:

1. **Upload** - Document ingestion and versioning
2. **Process** - Text extraction, span building, embeddings
3. **Search** - Semantic and keyword search
4. **Evidence Pack** - Juris-AGI integration point

---

## Troubleshooting

### Services Not Starting

```bash
# Check service status
docker-compose ps

# View logs
make logs

# Reset and rebuild
make down
make up-build
```

### Database Issues

```bash
# Check PostgreSQL
make db-shell

# Run migrations manually
make migrate

# Full reset (WARNING: destroys data)
make db-reset
```

### Worker Issues

```bash
# Check worker logs
docker-compose logs worker

# Check queue status
make queue-status

# Restart worker
docker-compose restart worker
```

---

## Project Structure

```
evidence-repository/
├── src/evidence_repository/
│   ├── api/              # FastAPI routes
│   │   └── routes/       # Endpoint handlers
│   ├── db/               # Database engine
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── storage/          # File storage abstraction
│   ├── extraction/       # Text extraction (LovePDF)
│   ├── embeddings/       # OpenAI embeddings
│   ├── services/         # Business logic
│   ├── queue/            # Redis/RQ job queue
│   ├── config.py         # Settings
│   ├── worker.py         # RQ worker entry
│   └── main.py           # FastAPI app
├── alembic/              # Database migrations
├── tests/                # Test suite
├── scripts/              # Utility scripts
├── data/                 # Local file storage
├── docker-compose.yml    # Service orchestration
├── Dockerfile            # Container build
├── Makefile              # Common commands
└── pyproject.toml        # Python project config
```

---

## License

MIT
