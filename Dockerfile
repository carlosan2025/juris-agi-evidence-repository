# Evidence Repository API Dockerfile
# Multi-stage build for optimal image size

# ============================================================================
# Build stage
# ============================================================================
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir build && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -e .

# ============================================================================
# Runtime stage
# ============================================================================
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user for security
RUN groupadd --gid 1000 evidence && \
    useradd --uid 1000 --gid evidence --shell /bin/bash --create-home evidence

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder and install
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code
COPY --chown=evidence:evidence src/ ./src/
COPY --chown=evidence:evidence alembic/ ./alembic/
COPY --chown=evidence:evidence alembic.ini ./

# Create data directory for local storage
RUN mkdir -p /app/data/uploads && chown -R evidence:evidence /app/data

# Switch to non-root user
USER evidence

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default command
CMD ["uvicorn", "evidence_repository.main:app", "--host", "0.0.0.0", "--port", "8000"]
