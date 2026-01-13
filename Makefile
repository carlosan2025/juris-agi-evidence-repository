# Evidence Repository Makefile
# Local MVP commands for development and testing

.PHONY: help install up down build logs clean test lint format migrate shell db-shell redis-cli

# Default target
help:
	@echo "Evidence Repository - Local MVP Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install     Install Python dependencies locally"
	@echo "  make build       Build Docker images"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make up          Start all services (api, worker, postgres, redis)"
	@echo "  make down        Stop all services"
	@echo "  make restart     Restart all services"
	@echo "  make logs        View all service logs"
	@echo "  make logs-api    View API logs only"
	@echo "  make logs-worker View Worker logs only"
	@echo ""
	@echo "Database:"
	@echo "  make migrate     Run database migrations"
	@echo "  make db-shell    Open PostgreSQL shell"
	@echo "  make db-reset    Reset database (WARNING: destroys data)"
	@echo ""
	@echo "Redis:"
	@echo "  make redis-cli   Open Redis CLI"
	@echo "  make queue-status Show job queue status"
	@echo ""
	@echo "Testing:"
	@echo "  make test        Run all tests"
	@echo "  make test-unit   Run unit tests only"
	@echo "  make test-int    Run integration tests only"
	@echo "  make test-cov    Run tests with coverage"
	@echo ""
	@echo "Development:"
	@echo "  make lint        Run linters (ruff)"
	@echo "  make format      Auto-format code"
	@echo "  make shell       Open Python shell with app context"
	@echo "  make dev-api     Run API locally (outside Docker)"
	@echo "  make dev-worker  Run worker locally (outside Docker)"
	@echo ""
	@echo "Monitoring:"
	@echo "  make up-monitor  Start with RQ dashboard"
	@echo "  make health      Check service health"

# =============================================================================
# Setup
# =============================================================================

install:
	pip install -e ".[dev]"

build:
	docker-compose build

# =============================================================================
# Docker Compose
# =============================================================================

up:
	docker-compose up -d
	@echo ""
	@echo "Services started!"
	@echo "  API:      http://localhost:8000"
	@echo "  Docs:     http://localhost:8000/api/v1/docs"
	@echo "  Postgres: localhost:5432"
	@echo "  Redis:    localhost:6379"

up-build:
	docker-compose up -d --build

up-monitor:
	docker-compose --profile monitoring up -d
	@echo ""
	@echo "Services started with monitoring!"
	@echo "  API:          http://localhost:8000"
	@echo "  RQ Dashboard: http://localhost:9181"

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f api

logs-worker:
	docker-compose logs -f worker

# =============================================================================
# Database
# =============================================================================

migrate:
	docker-compose exec api alembic upgrade head

migrate-local:
	alembic upgrade head

db-shell:
	docker-compose exec postgres psql -U evidence -d evidence_repository

db-reset:
	@echo "WARNING: This will destroy all data!"
	@read -p "Are you sure? (y/N) " confirm && [ "$$confirm" = "y" ]
	docker-compose down -v
	docker-compose up -d postgres redis
	@sleep 5
	docker-compose up migrations
	docker-compose up -d

# =============================================================================
# Redis
# =============================================================================

redis-cli:
	docker-compose exec redis redis-cli

queue-status:
	@echo "Queue Status:"
	@docker-compose exec redis redis-cli keys "rq:*" | head -20
	@echo ""
	@echo "Jobs by status:"
	@docker-compose exec redis redis-cli llen rq:queue:evidence_jobs 2>/dev/null || echo "  evidence_jobs: 0"
	@docker-compose exec redis redis-cli llen rq:queue:evidence_jobs_high 2>/dev/null || echo "  evidence_jobs_high: 0"
	@docker-compose exec redis redis-cli llen rq:queue:evidence_jobs_low 2>/dev/null || echo "  evidence_jobs_low: 0"

# =============================================================================
# Testing
# =============================================================================

test:
	pytest tests/ -v

test-unit:
	pytest tests/ -v -m "not integration"

test-int:
	pytest tests/ -v -m "integration"

test-cov:
	pytest tests/ -v --cov=evidence_repository --cov-report=html --cov-report=term-missing

test-integration-flow:
	pytest tests/test_integration_flow.py -v -s

# =============================================================================
# Development
# =============================================================================

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

shell:
	python -c "from evidence_repository.main import app; import code; code.interact(local=locals())"

dev-api:
	uvicorn evidence_repository.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	python -m evidence_repository.worker

# =============================================================================
# Monitoring & Health
# =============================================================================

health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/api/v1/health | python -m json.tool 2>/dev/null || echo "API: Not responding"
	@docker-compose exec redis redis-cli ping 2>/dev/null || echo "Redis: Not responding"
	@docker-compose exec postgres pg_isready -U evidence 2>/dev/null || echo "Postgres: Not responding"

# =============================================================================
# Quick Demo
# =============================================================================

demo:
	@echo "Running Evidence Repository Demo..."
	@echo ""
	@echo "1. Health check:"
	@curl -s http://localhost:8000/api/v1/health | python -m json.tool
	@echo ""
	@echo "2. Creating a project..."
	@curl -s -X POST http://localhost:8000/api/v1/projects \
		-H "X-API-Key: dev-key-12345" \
		-H "Content-Type: application/json" \
		-d '{"name": "Demo Project", "description": "Test project for demo"}' | python -m json.tool
	@echo ""
	@echo "3. Listing projects:"
	@curl -s http://localhost:8000/api/v1/projects \
		-H "X-API-Key: dev-key-12345" | python -m json.tool

# =============================================================================
# Cleanup
# =============================================================================

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage 2>/dev/null || true

clean-data:
	@echo "WARNING: This will delete all uploaded files!"
	@read -p "Are you sure? (y/N) " confirm && [ "$$confirm" = "y" ]
	rm -rf data/files/* data/test_files/* 2>/dev/null || true
