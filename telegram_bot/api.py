"""Thin wrapper around the Telegram Bot HTTP API.

Deliberately minimal -- a couple of httpx calls -- instead of depending on
a full Telegram bot framework, to keep this project's dependency footprint
small (consistent with the base jacob-bd project's own philosophy of
few, well-chosen dependencies). Only long polling (getUpdates) is used, so
no public HTTPS endpoint is required to run this locally.
"""

from __future__ import annotations

import httpx

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAPIError(Exception):
    """Raised when the Telegram Bot API responds with ok: false."""


class TelegramClient:
    def __init__(self, token: str, *, timeout: float = 35.0) -> None:
        self._base_url = f"{TELEGRAM_API_BASE}/bot{token}"
        self._http = httpx.Client(timeout=timeout)

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict]:
        """Long-poll for new updates. `timeout` is the long-poll wait, in seconds."""
        params: dict[str, int] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = self._http.get(f"{self._base_url}/getUpdates", params=params)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(data.get("description", "unknown error"))
        return data["result"]

    def send_message(self, chat_id: int, text: str) -> None:
        response = self._http.post(
            f"{self._base_url}/sendMessage", json={"chat_id": chat_id, "text": text}
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramAPIError(data.get("description", "unknown error"))

    def close(self) -> None:
        self._http.close()
