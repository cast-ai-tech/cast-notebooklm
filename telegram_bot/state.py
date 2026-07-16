"""Per-chat state for the Telegram bot: which notebook/profile a chat is
currently talking to, and the last /notebooks listing (so /usar <number>
can resolve a short number instead of making people type a UUID on their
phone).

Persisted as JSON under the same storage directory the rest of the project
uses for credentials (~/.notebooklm-mcp-cli/), so state survives restarts.
This file holds no secrets (just notebook IDs and profile names), so unlike
core/auth.py it is not encrypted.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

STATE_FILE_NAME = "telegram_chat_state.json"

_lock = threading.Lock()


def _state_file() -> Path:
    from notebooklm_tools.utils.config import get_storage_dir

    return get_storage_dir() / STATE_FILE_NAME


def _load() -> dict[str, Any]:
    path = _state_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, Any]) -> None:
    _state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _entry(chat_id: int, data: dict[str, Any]) -> dict[str, Any]:
    return data.get(str(chat_id), {})


def get_profile(chat_id: int) -> str:
    with _lock:
        return _entry(chat_id, _load()).get("profile", "default")


def set_profile(chat_id: int, profile: str) -> None:
    with _lock:
        data = _load()
        entry = data.get(str(chat_id), {})
        entry["profile"] = profile
        data[str(chat_id)] = entry
        _save(data)


def get_active_notebook_id(chat_id: int) -> str | None:
    with _lock:
        return _entry(chat_id, _load()).get("notebook_id")


def set_active_notebook_id(chat_id: int, notebook_id: str) -> None:
    with _lock:
        data = _load()
        entry = data.get(str(chat_id), {})
        entry["notebook_id"] = notebook_id
        data[str(chat_id)] = entry
        _save(data)


def get_last_list(chat_id: int) -> dict[str, str]:
    with _lock:
        return _entry(chat_id, _load()).get("last_list", {})


def set_last_list(chat_id: int, index_map: dict[str, str]) -> None:
    with _lock:
        data = _load()
        entry = data.get(str(chat_id), {})
        entry["last_list"] = index_map
        data[str(chat_id)] = entry
        _save(data)
