"""Vercel serverless function entry point for FastAPI.

This file adapts the FastAPI application to run as a Vercel serverless function.
"""

import sys
import traceback
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

try:
    from mangum import Mangum
    from evidence_repository.main import app

    # Mangum adapter for AWS Lambda / Vercel serverless
    handler = Mangum(app, lifespan="off")
except Exception as e:
    # Create a simple error handler if import fails
    error_msg = f"Import error: {str(e)}\n{traceback.format_exc()}"
    print(error_msg)

    async def error_app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({
            "type": "http.response.body",
            "body": error_msg.encode(),
        })

    handler = Mangum(error_app, lifespan="off")
