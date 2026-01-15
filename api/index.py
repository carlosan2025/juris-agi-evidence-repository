"""Vercel serverless function entry point for FastAPI.

Vercel's Python runtime has native FastAPI support - no Mangum needed.
Just export the FastAPI app instance as 'app'.
"""

import logging
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def run_migrations() -> None:
    """Run Alembic migrations at startup."""
    from alembic.config import Config
    from alembic import command

    # Find the alembic directory
    project_root = Path(__file__).parent.parent
    alembic_dir = project_root / "alembic"
    alembic_ini = project_root / "alembic.ini"

    if not alembic_ini.exists():
        logger.warning(f"alembic.ini not found at {alembic_ini}, skipping migrations")
        return

    logger.info(f"Running database migrations from {alembic_dir}...")
    try:
        alembic_cfg = Config(str(alembic_ini))
        alembic_cfg.set_main_option("script_location", str(alembic_dir))
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        # Don't crash the app, just log the error


# Run migrations on cold start (only if enabled)
if os.environ.get("RUN_MIGRATIONS", "true").lower() == "true":
    run_migrations()

# Import and re-export the FastAPI app
# Vercel looks for 'app' variable automatically
from evidence_repository.main import app
