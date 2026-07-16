"""FastAPI dependencies: API key authentication and client resolution.

Neither of the two upstream projects this REST layer draws on authenticate
their HTTP transport: roomi-fields/notebooklm-mcp's Express wrapper has no
auth at all (binds 0.0.0.0 with CORS "*"), and the jacob-bd MCP HTTP
transport just refuses non-loopback binds instead of authenticating
requests. cast-notebooklm's REST API is meant to be reachable from
automation tools (n8n, Zapier, Make) across the network, so every route
here requires an API key.

Configuration: CAST_NLM_API_KEYS, a comma-separated list of accepted keys.
If unset, the API refuses to start (see main.py:run) rather than silently
running open.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.exceptions import AuthenticationError, ProfileNotFoundError

from . import client_pool

API_KEYS_ENV_VAR = "CAST_NLM_API_KEYS"


def get_configured_api_keys() -> set[str]:
    raw = os.environ.get(API_KEYS_ENV_VAR, "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _matches_any(candidate: str, keys: set[str]) -> bool:
    # Constant-time comparison per key to avoid leaking key length/prefix
    # via response timing.
    return any(hmac.compare_digest(candidate, key) for key in keys)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Validate the X-API-Key header. Raises 401/403 on failure."""
    keys = get_configured_api_keys()
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header")
    if not _matches_any(x_api_key, keys):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return x_api_key


def get_notebooklm_client(profile: str = client_pool.DEFAULT_PROFILE):
    """Resolve a NotebookLMClient for `profile`, raising a clean HTTP error.

    Not itself a FastAPI dependency (profile is usually a request-body field,
    not a path/query param) -- routers call this directly after validating
    the body, then pass the client into the corresponding service function.
    """
    try:
        return client_pool.get_client(profile)
    except ProfileNotFoundError as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                f"No saved credentials for profile '{profile}'. "
                f"Run 'nlm login --profile {profile}' first."
            ),
        ) from e
    except AuthenticationError as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Profile '{profile}' credentials are invalid or corrupted: {e}",
        ) from e


def list_known_profiles() -> list[str]:
    return AuthManager.list_profiles()
