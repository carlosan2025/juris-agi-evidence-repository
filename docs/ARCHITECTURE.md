# Evidence Repository - Technical Architecture

**Version**: 1.0.0
**Status**: LOCKED
**Last Updated**: 2026-01-13

This document defines the canonical technical stack, architectural conventions, and module boundaries for the Evidence Repository. All implementation decisions must conform to this specification.

---

## 1. Technology Stack (LOCKED)

| Component | Technology | Version | Notes |
|-----------|------------|---------|-------|
| Language | Python | 3.11+ | Type hints required |
| API Framework | FastAPI | 0.109+ | OpenAPI-first |
| Server | Uvicorn | 0.27+ | ASGI server |
| Database | PostgreSQL | 16+ | Primary data store |
| Vector Storage | pgvector | 0.6+ | Extension in Postgres |
| ORM | SQLAlchemy | 2.0+ | Async mode required |
| Migrations | Alembic | 1.13+ | Autogenerate enabled |
| Job Queue | Redis + RQ | Redis 7+, RQ 1.16+ | Local MVP |
| Embeddings | OpenAI API | text-embedding-3-small | Configurable model |
| PDF Extraction | LovePDF API | - | Third-party service |
| Local Storage | Filesystem | - | `./data/uploads/` |
| Cloud Storage | AWS S3 | boto3 | Future migration |
| Validation | Pydantic | 2.5+ | Request/response DTOs |
| HTTP Client | httpx | 0.26+ | Async requests |
| Auth (current) | API Key | - | X-API-Key header |
| Auth (future) | JWT | python-jose | Bearer token |
| Containerization | Docker | 24+ | Docker Compose v2 |

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL CLIENTS                                │
│                    (Juris-AGI, Web UI, CLI Tools, etc.)                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FASTAPI APPLICATION                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         API LAYER (api/)                                 ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ││
│  │  │   routes/    │  │ dependencies │  │  middleware  │  │   schemas/   │ ││
│  │  │  (handlers)  │  │    (DI)      │  │   (audit)    │  │   (DTOs)     │ ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                       │                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                       SERVICE LAYER (services/)                          ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ││
│  │  │  document_   │  │   project_   │  │   search_    │  │  evidence_   │ ││
│  │  │   service    │  │   service    │  │   service    │  │   service    │ ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                       │                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         CORE LAYER                                       ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ││
│  │  │  ingestion/  │  │ extraction/  │  │  embeddings/ │  │   storage/   │ ││
│  │  │  (upload)    │  │  (LovePDF)   │  │   (OpenAI)   │  │ (local/S3)   │ ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │                              │
         ▼                              ▼                              ▼
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│   PostgreSQL    │          │      Redis      │          │  File Storage   │
│   + pgvector    │          │   (Job Queue)   │          │  (Local / S3)   │
└─────────────────┘          └─────────────────┘          └─────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RQ WORKER(S)                                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         QUEUE MODULE (queue/)                            ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   ││
│  │  │ connection   │  │    jobs      │  │    tasks     │                   ││
│  │  │   (redis)    │  │  (manager)   │  │  (handlers)  │                   ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                       │                                      │
│                    (reuses: storage/, extraction/, embeddings/)              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Folder Structure (CANONICAL)

```
evidence-repository/
├── .env.example                    # Environment template
├── .gitignore
├── alembic.ini                     # Alembic configuration
├── docker-compose.yml              # Container orchestration
├── Dockerfile                      # Application container
├── pyproject.toml                  # Dependencies and scripts
├── README.md                       # Quick start guide
│
├── alembic/                        # Database migrations
│   ├── env.py                      # Migration environment
│   ├── script.py.mako              # Migration template
│   └── versions/                   # Migration files
│       └── 001_initial_schema.py
│
├── data/                           # Local file storage (gitignored)
│   └── uploads/                    # Document files
│
├── docs/                           # Documentation
│   └── ARCHITECTURE.md             # This file
│
├── scripts/                        # Utility scripts
│   └── init-db.sql                 # Database initialization
│
├── src/
│   └── evidence_repository/
│       ├── __init__.py
│       ├── config.py               # Pydantic Settings
│       ├── main.py                 # FastAPI application
│       ├── worker.py               # RQ worker entry point
│       │
│       ├── api/                    # HTTP API layer
│       │   ├── __init__.py
│       │   ├── dependencies.py     # DI: auth, db, storage
│       │   ├── middleware.py       # Audit logging, error handling
│       │   └── routes/             # Endpoint handlers
│       │       ├── __init__.py     # Route aggregation
│       │       ├── documents.py    # /documents
│       │       ├── evidence.py     # /spans, /claims, /metrics, /evidence-packs
│       │       ├── health.py       # /health
│       │       ├── jobs.py         # /jobs
│       │       ├── projects.py     # /projects
│       │       └── search.py       # /search
│       │
│       ├── db/                     # Database layer
│       │   ├── __init__.py
│       │   ├── engine.py           # Async SQLAlchemy engine
│       │   └── session.py          # Session factory
│       │
│       ├── models/                 # SQLAlchemy ORM models
│       │   ├── __init__.py         # Model exports
│       │   ├── audit.py            # AuditLog, AuditAction
│       │   ├── base.py             # Base model, mixins
│       │   ├── document.py         # Document, DocumentVersion
│       │   ├── embedding.py        # EmbeddingChunk
│       │   ├── evidence.py         # Span, Claim, Metric, EvidencePack
│       │   └── project.py          # Project, ProjectDocument
│       │
│       ├── schemas/                # Pydantic DTOs
│       │   ├── __init__.py         # Schema exports
│       │   ├── common.py           # Shared schemas
│       │   ├── document.py         # Document DTOs
│       │   ├── evidence.py         # Evidence DTOs
│       │   ├── job.py              # Job DTOs
│       │   ├── project.py          # Project DTOs
│       │   └── search.py           # Search DTOs
│       │
│       ├── services/               # Business logic
│       │   ├── __init__.py
│       │   ├── document_service.py # Document operations
│       │   ├── evidence_service.py # Evidence operations
│       │   ├── project_service.py  # Project operations
│       │   └── search_service.py   # Vector search
│       │
│       ├── storage/                # File storage abstraction
│       │   ├── __init__.py
│       │   ├── base.py             # StorageBackend ABC
│       │   ├── local.py            # LocalFilesystemStorage
│       │   └── s3.py               # S3Storage (stubbed)
│       │
│       ├── queue/                  # Job queue management
│       │   ├── __init__.py
│       │   ├── connection.py       # Redis connection, queues
│       │   ├── jobs.py             # JobManager, JobInfo
│       │   └── tasks.py            # Background task implementations
│       │
│       ├── ingestion/              # Document upload pipeline
│       │   ├── __init__.py
│       │   └── service.py          # IngestionService
│       │
│       ├── extraction/             # Text extraction
│       │   ├── __init__.py
│       │   ├── service.py          # ExtractionService
│       │   └── lovepdf.py          # LovePDF client
│       │
│       └── embeddings/             # Vector embeddings
│           ├── __init__.py
│           ├── chunker.py          # Text chunking
│           ├── openai_client.py    # OpenAI client
│           └── service.py          # EmbeddingService
│
└── tests/                          # Test suite
    ├── __init__.py
    ├── conftest.py                 # Pytest fixtures
    └── ...
```

---

## 4. Module Boundaries

### 4.1 API Layer (`api/`)

**Responsibility**: HTTP request handling, authentication, routing

**Rules**:
- Routes MUST be async functions
- Routes MUST use Pydantic schemas for request/response
- Routes MUST NOT contain business logic (delegate to services)
- Routes MUST NOT directly access database (use dependencies)
- Authentication via `get_current_user` dependency

**Files**:
| File | Purpose |
|------|---------|
| `dependencies.py` | DI providers: auth, db session, storage backend |
| `middleware.py` | Request/response interceptors |
| `routes/*.py` | Endpoint handlers grouped by domain |

### 4.2 Database Layer (`db/`)

**Responsibility**: Connection management, session lifecycle

**Rules**:
- Engine MUST be async (`asyncpg` driver)
- Sessions MUST be scoped to request lifecycle
- No raw SQL (use SQLAlchemy ORM)

**Files**:
| File | Purpose |
|------|---------|
| `engine.py` | `create_async_engine` configuration |
| `session.py` | `async_sessionmaker` factory |

### 4.3 Models Layer (`models/`)

**Responsibility**: ORM entity definitions, database schema

**Rules**:
- All models inherit from `BaseModel` (provides id, timestamps)
- UUIDs as primary keys
- Relationships defined via SQLAlchemy relationship()
- JSON columns use `JSONB` type
- Vector columns use pgvector's `Vector` type

**Entities**:
| Model | Description |
|-------|-------------|
| `Document` | Global document asset |
| `DocumentVersion` | Immutable document version |
| `Project` | Evaluation context |
| `ProjectDocument` | Document-Project link (with pinned version) |
| `Span` | Precise document locator |
| `Claim` | Evidence assertion |
| `Metric` | Quantitative evidence |
| `EvidencePack` | Bundled evidence for export |
| `EmbeddingChunk` | Text chunk with vector |
| `AuditLog` | Immutable audit trail |

### 4.4 Schemas Layer (`schemas/`)

**Responsibility**: Request/response validation, API contracts

**Rules**:
- All schemas inherit from `pydantic.BaseModel`
- Use `ConfigDict(from_attributes=True)` for ORM compatibility
- Separate Create/Update/Response schemas
- No business logic in schemas

**Naming Convention**:
- `{Entity}Create` - POST request body
- `{Entity}Update` - PATCH request body
- `{Entity}Response` - API response

### 4.5 Services Layer (`services/`)

**Responsibility**: Business logic orchestration

**Rules**:
- Services are stateless
- Services receive db session via parameter
- Services coordinate between models and external systems
- Services handle validation and authorization checks
- Services raise domain exceptions (not HTTP exceptions)

### 4.6 Storage Layer (`storage/`)

**Responsibility**: File I/O abstraction

**Rules**:
- All storage operations MUST be async
- Storage backend selected via `STORAGE_BACKEND` env var
- S3 implementation stubbed for future migration
- Storage keys use structured paths: `{document_id}/{version_id}/{filename}`

**Interface**:
```python
class StorageBackend(ABC):
    async def upload(key: str, data: bytes, content_type: str) -> str
    async def download(key: str) -> bytes
    async def delete(key: str) -> bool
    async def get_url(key: str, expires_in: int = 3600) -> str
    async def exists(key: str) -> bool
```

### 4.7 Queue Layer (`queue/`)

**Responsibility**: Background job management

**Rules**:
- Jobs MUST be idempotent
- Jobs MUST reference document_id + version_id
- Job status stored in Redis
- Worker processes run in separate containers

**Priority Queues**:
| Queue | Purpose |
|-------|---------|
| `high` | Text extraction (user-facing latency) |
| `evidence_jobs` | Normal processing (default) |
| `low` | Bulk operations |

### 4.8 Ingestion Layer (`ingestion/`)

**Responsibility**: Document upload pipeline

**Rules**:
- Compute content hash (SHA-256) on upload
- Detect duplicates via hash
- Create new version for each upload
- Store file via storage backend
- Return immediately (processing is async)

### 4.9 Extraction Layer (`extraction/`)

**Responsibility**: Text extraction from documents

**Rules**:
- Support multiple file types
- LovePDF for PDFs
- Direct read for text files
- Extraction runs in worker (not API process)
- Update `extraction_status` on document version

**Supported Types**:
| Extension | Handler |
|-----------|---------|
| `.pdf` | LovePDF API |
| `.txt`, `.md` | Direct read |
| `.csv` | CSV parser |
| `.xlsx` | openpyxl |
| `.png`, `.jpg`, `.jpeg`, `.webp` | OCR (future) |

### 4.10 Embeddings Layer (`embeddings/`)

**Responsibility**: Vector generation for semantic search

**Rules**:
- Text chunked before embedding
- Chunk size/overlap configurable
- OpenAI API for embedding generation
- Chunks stored with source document reference
- pgvector for similarity search

---

## 5. Configuration System

**Implementation**: Pydantic BaseSettings

**Location**: `src/evidence_repository/config.py`

**Features**:
- Environment variable loading (`.env` file support)
- Type validation and coercion
- Default values for development
- Field validators for complex types
- Singleton via `@lru_cache`

**Configuration Groups**:

```python
class Settings(BaseSettings):
    # Application
    app_name: str = "Evidence Repository"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # API
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Authentication
    api_keys: list[str]  # Comma-separated in env
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30

    # Database
    database_url: str  # postgresql+asyncpg://...
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = "./data/uploads"
    # S3 settings...

    # External Services
    lovepdf_public_key: str
    lovepdf_secret_key: str
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_name: str = "evidence_jobs"
    redis_job_timeout: int = 3600
    redis_result_ttl: int = 86400

    # Bulk Ingestion
    bulk_ingestion_batch_size: int = 50
    url_download_timeout: int = 300
    max_file_size_mb: int = 100
    supported_extensions: list[str]

    # CORS
    cors_origins: list[str]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
```

---

## 6. Logging Strategy

### 6.1 Log Format (Structured JSON)

**Production Format**:
```json
{
  "timestamp": "2026-01-13T10:30:00.000Z",
  "level": "INFO",
  "logger": "evidence_repository.api.routes.documents",
  "message": "Document uploaded",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "document_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": "user-123",
  "duration_ms": 45
}
```

**Development Format**:
```
2026-01-13 10:30:00 - evidence_repository.api - INFO - Document uploaded
```

### 6.2 Log Levels

| Level | Usage |
|-------|-------|
| `DEBUG` | Detailed debugging (not in production) |
| `INFO` | Normal operations, request lifecycle |
| `WARNING` | Recoverable issues, deprecations |
| `ERROR` | Failures requiring attention |
| `CRITICAL` | System failures |

### 6.3 Audit Logging

**Purpose**: Compliance, forensics, debugging

**Stored in**: `audit_logs` table

**Captured**:
- Action type (enum)
- Entity type and ID
- Actor ID
- Request context (IP, user-agent, request-id)
- Timestamp
- Details (JSON)

**Audited Actions**:
- Document: upload, download, delete, extract
- Project: create, update, delete
- Document-Project: attach, detach
- Evidence: create spans, claims, metrics
- Search: queries performed

---

## 7. Error Handling Strategy

### 7.1 API Errors

**Standard Error Response**:
```json
{
  "error": "error_code",
  "message": "Human-readable description",
  "details": {
    "field": "additional context",
    "request_id": "uuid"
  }
}
```

**HTTP Status Codes**:
| Code | Usage |
|------|-------|
| 400 | Validation errors, bad request |
| 401 | Authentication required/failed |
| 403 | Authorization denied |
| 404 | Resource not found |
| 409 | Conflict (duplicate, state conflict) |
| 422 | Unprocessable entity |
| 500 | Internal server error |

**Implementation**:
```python
# In routes - use HTTPException
raise HTTPException(
    status_code=404,
    detail={"error": "document_not_found", "message": "Document not found"}
)

# Global middleware catches unhandled exceptions
class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception("Unhandled exception")
            return JSONResponse(
                status_code=500,
                content={"error": "internal_error", "message": "An error occurred"}
            )
```

### 7.2 Worker/Job Errors

**Handling Strategy**:
1. Catch exceptions in task functions
2. Log error with full context
3. Update job status to FAILED
4. Store error message in job result
5. Do NOT crash worker process

**Implementation**:
```python
def task_process_document(document_id: str, version_id: str):
    try:
        # Processing logic
        job_manager.update_status(job_id, JobStatus.FINISHED)
    except Exception as e:
        logger.exception(f"Task failed: {e}")
        job_manager.update_status(
            job_id,
            JobStatus.FAILED,
            error=str(e)
        )
```

### 7.3 Domain Exceptions

**Custom Exceptions** (in `utils/exceptions.py`):
```python
class EvidenceRepositoryError(Exception):
    """Base exception for application errors."""

class StorageError(EvidenceRepositoryError):
    """Storage operation failed."""

class ExtractionError(EvidenceRepositoryError):
    """Text extraction failed."""

class EmbeddingError(EvidenceRepositoryError):
    """Embedding generation failed."""

class ValidationError(EvidenceRepositoryError):
    """Business validation failed."""
```

---

## 8. Docker Compose Configuration

```yaml
version: "3.9"

services:
  # =============================================================================
  # API Service
  # =============================================================================
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: evidence-api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://evidence:evidence_secret@postgres:5432/evidence_repository
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./src:/app/src:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - evidence-network

  # =============================================================================
  # Worker Service
  # =============================================================================
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: evidence-worker
    command: python -m evidence_repository.worker
    environment:
      - DATABASE_URL=postgresql+psycopg2://evidence:evidence_secret@postgres:5432/evidence_repository
      - REDIS_URL=redis://redis:6379/0
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./src:/app/src:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      migrations:
        condition: service_completed_successfully
    deploy:
      replicas: 1
    networks:
      - evidence-network

  # =============================================================================
  # PostgreSQL + pgvector
  # =============================================================================
  postgres:
    image: pgvector/pgvector:pg16
    container_name: evidence-postgres
    environment:
      - POSTGRES_USER=evidence
      - POSTGRES_PASSWORD=evidence_secret
      - POSTGRES_DB=evidence_repository
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U evidence -d evidence_repository"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - evidence-network

  # =============================================================================
  # Redis
  # =============================================================================
  redis:
    image: redis:7-alpine
    container_name: evidence-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - evidence-network

  # =============================================================================
  # Migrations (one-shot)
  # =============================================================================
  migrations:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: evidence-migrations
    command: alembic upgrade head
    environment:
      - DATABASE_URL=postgresql+asyncpg://evidence:evidence_secret@postgres:5432/evidence_repository
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"
    networks:
      - evidence-network

  # =============================================================================
  # RQ Dashboard (optional monitoring)
  # =============================================================================
  rq-dashboard:
    image: eoranged/rq-dashboard:latest
    container_name: evidence-rq-dashboard
    environment:
      - RQ_DASHBOARD_REDIS_URL=redis://redis:6379/0
    ports:
      - "9181:9181"
    depends_on:
      - redis
    profiles:
      - monitoring
    networks:
      - evidence-network

networks:
  evidence-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

---

## 9. Architectural Principles

### 9.1 Non-Blocking API

**Principle**: API MUST NEVER block on document processing

**Implementation**:
- All uploads enqueue jobs and return immediately
- Job ID returned in response for status tracking
- Long-running operations (extraction, embedding) run in workers
- `/jobs/{job_id}` endpoint for progress polling

### 9.2 Idempotent Processing

**Principle**: Processing MUST be idempotent and restartable

**Implementation**:
- Jobs can be safely retried
- Status checks prevent duplicate processing
- Failed jobs can be requeued
- No side effects on repeated execution

### 9.3 Global Documents

**Principle**: Documents are global assets; projects only reference them

**Implementation**:
- `Document` table holds the asset
- `ProjectDocument` junction table links documents to projects
- Deleting a project doesn't delete documents
- Same document can be attached to multiple projects

### 9.4 Version Stability

**Principle**: All derived data MUST reference document_id + version_id

**Implementation**:
- `DocumentVersion` is immutable after creation
- Spans reference `document_version_id`
- Embedding chunks reference `document_version_id`
- Citations remain stable across document updates

### 9.5 Storage Abstraction

**Principle**: Storage backend must be pluggable

**Implementation**:
- `StorageBackend` abstract base class
- `LocalFilesystemStorage` for development
- `S3Storage` stubbed for production migration
- Backend selected via `STORAGE_BACKEND` env var

---

## 10. API Endpoint Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/documents` | Upload document (sync) |
| GET | `/api/v1/documents` | List documents |
| GET | `/api/v1/documents/{id}` | Get document |
| DELETE | `/api/v1/documents/{id}` | Soft delete document |
| GET | `/api/v1/documents/{id}/versions` | List versions |
| GET | `/api/v1/documents/{id}/versions/{vid}/download` | Download version |
| POST | `/api/v1/documents/{id}/extract` | Trigger extraction |
| POST | `/api/v1/projects` | Create project |
| GET | `/api/v1/projects` | List projects |
| GET | `/api/v1/projects/{id}` | Get project |
| PATCH | `/api/v1/projects/{id}` | Update project |
| DELETE | `/api/v1/projects/{id}` | Delete project |
| POST | `/api/v1/projects/{id}/documents` | Attach document |
| DELETE | `/api/v1/projects/{id}/documents/{doc_id}` | Detach document |
| POST | `/api/v1/search` | Semantic search |
| POST | `/api/v1/search/projects/{id}` | Search in project |
| POST | `/api/v1/spans` | Create span |
| GET | `/api/v1/spans/{id}` | Get span |
| POST | `/api/v1/claims` | Create claim |
| POST | `/api/v1/metrics` | Create metric |
| POST | `/api/v1/evidence-packs` | Create evidence pack |
| GET | `/api/v1/evidence-packs/{id}` | Get evidence pack |
| POST | `/api/v1/evidence-packs/{id}/items` | Add item to pack |
| GET | `/api/v1/evidence-packs/{id}/export` | Export pack |
| GET | `/api/v1/jobs/{id}` | Get job status |
| GET | `/api/v1/jobs` | List jobs |
| DELETE | `/api/v1/jobs/{id}` | Cancel job |
| POST | `/api/v1/jobs/upload` | Async upload |
| POST | `/api/v1/jobs/ingest/folder` | Bulk folder ingest |
| POST | `/api/v1/jobs/ingest/url` | URL ingest |
| POST | `/api/v1/jobs/batch/extract` | Batch extraction |
| POST | `/api/v1/jobs/batch/embed` | Batch embedding |

---

## 11. Future Migration Path

### AWS Migration Checklist

1. **Storage**: Switch `STORAGE_BACKEND=s3`, implement `S3Storage` methods
2. **Queue**: Replace RQ with SQS, update `queue/` module
3. **Workers**: Deploy as ECS tasks consuming SQS
4. **Database**: Migrate to RDS PostgreSQL with pgvector
5. **Redis**: Migrate to ElastiCache (for job status, if retained)
6. **Secrets**: Use AWS Secrets Manager
7. **Logging**: Ship to CloudWatch

---

## 12. Verification Checklist

After deployment, verify:

- [ ] `docker-compose up --build` starts all services
- [ ] Health check: `curl http://localhost:8000/api/v1/health`
- [ ] OpenAPI docs: `http://localhost:8000/api/v1/docs`
- [ ] Upload document via API
- [ ] Verify file in `data/uploads/`
- [ ] Verify metadata in PostgreSQL
- [ ] Check job queued in Redis
- [ ] Verify worker processes job
- [ ] Check audit log entries

---

**Document Status**: LOCKED

Changes to this architecture require team review and version increment.
