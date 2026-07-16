"""cast-notebooklm REST API -- FastAPI wrapper around notebooklm_tools.services.

Mirrors the shape of roomi-fields/notebooklm-mcp's Express HTTP wrapper (MIT
licensed, see CREDITS.md): a thin transport layer over the same service
functions the CLI (`nlm`) and MCP server already call, so all three
transports share one source of truth for business logic. Routers here call
straight into notebooklm_tools.services.* and never into core/* directly,
matching the layering rule the jacob-bd base already enforces between its
own cli/ and mcp/ layers.

Unlike that original, every route requires an API key (see deps.py) -- this
REST layer is meant to be reachable across the network (e.g. from an n8n
instance), and neither upstream project this is based on authenticates its
HTTP transport.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from notebooklm_tools.services.errors import ServiceError, ValidationError

from .deps import API_KEYS_ENV_VAR, get_configured_api_keys
from .routers import chat, notebooks, sources, studio

_STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)

app = FastAPI(
    title="cast-notebooklm REST API",
    description=(
        "REST wrapper around the NotebookLM CLI/MCP services, for use from "
        "automation tools (n8n, Zapier, Make). Every route requires an "
        f"X-API-Key header matching a key configured via {API_KEYS_ENV_VAR}."
    ),
    version="0.1.0",
)

app.include_router(notebooks.router)
app.include_router(chat.router)
app.include_router(sources.router)
app.include_router(studio.router)

# Static dashboard (plain HTML/CSS/JS, no build step -- see static/app.js).
# It's just the frontend shell; every data call it makes still goes through
# the routers above and requires the API key the user enters in the page.
app.mount("/dashboard", StaticFiles(directory=_STATIC_DIR, html=True), name="dashboard")


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/")


@app.exception_handler(ValidationError)
async def _validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"success": False, "error": exc.user_message})


@app.exception_handler(ServiceError)
async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    # ValidationError is a ServiceError subclass; its own handler above
    # (registered separately) takes precedence for that type.
    return JSONResponse(status_code=502, content={"success": False, "error": exc.user_message})


@app.get("/health")
async def health() -> dict:
    """Unauthenticated liveness check. Does not touch NotebookLM or require an API key."""
    return {"success": True, "status": "ok"}


def create_app() -> FastAPI:
    """Return the configured FastAPI app (for use with an external ASGI server)."""
    return app


def run() -> None:
    """Entry point for the `cast-notebooklm-api` console script."""
    import uvicorn

    if not get_configured_api_keys():
        raise SystemExit(
            f"{API_KEYS_ENV_VAR} is not set. Refusing to start the REST API without at "
            "least one API key configured -- set it to a comma-separated list of secrets "
            "automation tools will send as the X-API-Key header."
        )

    host = os.environ.get("CAST_NLM_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CAST_NLM_API_PORT", "8008"))
    logger.info(f"Starting cast-notebooklm REST API on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
