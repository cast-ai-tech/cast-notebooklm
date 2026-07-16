"""Per-profile NotebookLMClient factory for the REST API.

The MCP server (mcp/tools/_utils.py::get_client) keeps a single
process-wide client singleton -- one active Google account per server
process. The REST API needs multiple accounts addressable concurrently
(this is the blueprint sketched in the jacob-bd base's
docs/MULTI_USER_ANALYSIS.md, not implemented there), so instead of a
singleton this keeps a small in-memory pool of clients keyed by profile
name, built from notebooklm_tools.core.auth.AuthManager -- the same
encrypted profile storage the CLI (`nlm login switch <profile>`) and MCP
server already use. Adding/removing accounts is entirely a CLI concern;
this module just picks the right already-authenticated profile per request.

Clients are cheap to construct (see core/client.py). A cached client is
reused until the on-disk profile is updated (e.g. `nlm login` re-authenticates
it), detected the same way mcp/tools/_utils.py::get_client() does: comparing
against the profile's last_validated timestamp.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.client import NotebookLMClient

DEFAULT_PROFILE = "default"


@dataclass
class _PooledClient:
    client: NotebookLMClient
    loaded_at: float  # source profile's last_validated timestamp


class ClientPool:
    """Thread-safe cache of NotebookLMClient instances, keyed by profile name."""

    def __init__(self) -> None:
        self._clients: dict[str, _PooledClient] = {}
        self._lock = threading.Lock()

    def get(self, profile_name: str = DEFAULT_PROFILE) -> NotebookLMClient:
        """Get (or build) the client for `profile_name`.

        Rebuilds the client if the on-disk profile was updated since the
        cached client was built.

        Raises:
            ProfileNotFoundError: if the profile has no saved credentials
                (propagated from AuthManager.load_profile).
            AuthenticationError: if the profile exists but is corrupted.
        """
        manager = AuthManager(profile_name)
        profile = manager.load_profile()
        loaded_at = profile.last_validated.timestamp() if profile.last_validated else 0.0

        with self._lock:
            pooled = self._clients.get(profile_name)
            if pooled is not None and pooled.loaded_at >= loaded_at:
                return pooled.client

            client = NotebookLMClient(
                cookies=profile.cookies,
                csrf_token=profile.csrf_token or "",
                session_id=profile.session_id or "",
                build_label=profile.build_label or "",
            )
            self._clients[profile_name] = _PooledClient(client=client, loaded_at=loaded_at)
            return client

    def invalidate(self, profile_name: str = DEFAULT_PROFILE) -> None:
        """Drop a cached client so the next get() rebuilds it from disk."""
        with self._lock:
            self._clients.pop(profile_name, None)

    def cached_profiles(self) -> list[str]:
        with self._lock:
            return list(self._clients)


# Process-wide pool, mirroring the module-level singleton pattern already
# used by mcp/tools/_utils.py (one pool per REST API process).
_pool = ClientPool()


def get_client(profile_name: str = DEFAULT_PROFILE) -> NotebookLMClient:
    """Module-level convenience wrapper around the shared pool."""
    return _pool.get(profile_name)


def invalidate_client(profile_name: str = DEFAULT_PROFILE) -> None:
    _pool.invalidate(profile_name)


def cached_profiles() -> list[str]:
    return _pool.cached_profiles()
