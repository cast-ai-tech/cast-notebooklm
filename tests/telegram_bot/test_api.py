"""Tests for telegram_bot/api.py -- thin Telegram Bot HTTP API wrapper."""

import httpx
import pytest

from telegram_bot.api import TelegramAPIError, TelegramClient


def _client_with_transport(handler) -> TelegramClient:
    client = TelegramClient("fake-token")
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


class TestGetUpdates:
    def test_returns_result_list(self):
        def handler(request):
            assert request.url.path == "/botfake-token/getUpdates"
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1}]})

        client = _client_with_transport(handler)
        assert client.get_updates() == [{"update_id": 1}]

    def test_passes_offset(self):
        seen = {}

        def handler(request):
            seen["offset"] = request.url.params.get("offset")
            return httpx.Response(200, json={"ok": True, "result": []})

        client = _client_with_transport(handler)
        client.get_updates(offset=42)
        assert seen["offset"] == "42"

    def test_raises_on_ok_false(self):
        def handler(request):
            return httpx.Response(200, json={"ok": False, "description": "bad token"})

        client = _client_with_transport(handler)
        with pytest.raises(TelegramAPIError, match="bad token"):
            client.get_updates()


class TestSendMessage:
    def test_posts_chat_id_and_text(self):
        seen = {}

        def handler(request):
            seen["body"] = request.read()
            return httpx.Response(200, json={"ok": True, "result": {}})

        client = _client_with_transport(handler)
        client.send_message(123, "hola")
        assert b'"chat_id":123' in seen["body"]
        assert b'"text":"hola"' in seen["body"]

    def test_raises_on_ok_false(self):
        def handler(request):
            return httpx.Response(200, json={"ok": False, "description": "chat not found"})

        client = _client_with_transport(handler)
        with pytest.raises(TelegramAPIError, match="chat not found"):
            client.send_message(123, "hola")
