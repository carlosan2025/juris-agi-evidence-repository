"""Simple test endpoint to debug Vercel Python."""

import sys
import json
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        result = {"status": "testing"}

        try:
            # Add src to path
            src_path = Path(__file__).parent.parent / "src"
            sys.path.insert(0, str(src_path))
            result["src_path"] = str(src_path)

            # Try importing config
            from evidence_repository.config import get_settings
            result["config_import"] = "ok"

            settings = get_settings()
            result["settings"] = {
                "app_name": repr(settings.app_name),
                "database_url": settings.database_url[:50] + "..." if settings.database_url else None,
                "storage_backend": settings.storage_backend,
                "cors_origins": settings.cors_origins[:3] if settings.cors_origins else None,
            }

            # Try importing app
            from evidence_repository.main import app
            result["app_import"] = "ok"
            result["app_title"] = repr(app.title)
            result["routes_count"] = len(app.routes)

            # List routes
            result["routes"] = [r.path for r in app.routes if hasattr(r, 'path')][:10]

            # Try Mangum handler
            from mangum import Mangum
            mangum_handler = Mangum(app, lifespan="off")
            result["mangum_handler"] = "ok"

            # Simulate a simple request to see what happens
            test_event = {
                "httpMethod": "GET",
                "path": "/api/v1/health",
                "headers": {},
                "queryStringParameters": None,
                "body": None,
                "isBase64Encoded": False,
                "requestContext": {
                    "http": {
                        "method": "GET",
                        "path": "/api/v1/health"
                    }
                },
                "version": "2.0"
            }

            # Try invoking the handler
            try:
                import asyncio
                response = asyncio.get_event_loop().run_until_complete(
                    mangum_handler.handler(test_event, {})
                ) if hasattr(mangum_handler, 'handler') else "no handler attr"
                result["test_invoke"] = str(response)[:500]
            except Exception as invoke_err:
                result["invoke_error"] = str(invoke_err)
                result["invoke_traceback"] = traceback.format_exc()

        except Exception as e:
            result["error"] = str(e)
            result["traceback"] = traceback.format_exc()

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())
        return
