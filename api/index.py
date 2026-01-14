"""Vercel serverless function entry point for FastAPI.

This file adapts the FastAPI application to run as a Vercel serverless function.
"""

import sys
import traceback
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
logger.info(f"Added {src_path} to sys.path")

try:
    logger.info("Importing Mangum...")
    from mangum import Mangum

    logger.info("Importing FastAPI app...")
    from evidence_repository.main import app

    logger.info(f"App imported successfully: {app.title}")
    logger.info(f"Routes count: {len(app.routes)}")

    # Mangum adapter for AWS Lambda / Vercel serverless
    # Use api_gateway_base_path to handle Vercel routing
    handler = Mangum(app, lifespan="off", api_gateway_base_path="")
    logger.info("Mangum handler created successfully")

except Exception as e:
    # Create a simple error handler if import fails
    error_msg = f"Import error: {str(e)}\n{traceback.format_exc()}"
    logger.error(error_msg)

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
