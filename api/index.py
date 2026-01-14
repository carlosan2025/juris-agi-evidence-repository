"""Vercel serverless function entry point for FastAPI.

Vercel's Python runtime has native FastAPI support - no Mangum needed.
Just export the FastAPI app instance as 'app'.
"""

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Import and re-export the FastAPI app
# Vercel looks for 'app' variable automatically
from evidence_repository.main import app
