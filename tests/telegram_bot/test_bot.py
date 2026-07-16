"""Tests for telegram_bot/bot.py -- startup guards and the poll loop."""

from unittest.mock import MagicMock

import pytest

from telegram_bot import bot


class TestParseAllowedUsers:
    def test_parses_comma_separated_ids(self):
        assert bot._parse_allowed_users("111, 222 ,333") == {111, 222, 333}

    def test_empty_string_yields_empty_set(self):
        assert bot._parse_allowed_users("") == set()

    def test_ignores_invalid_entries(self, caplog):
        assert bot._parse_allowed_users("111,not-a-number,222") == {111, 222}


class TestRunGuards:
    def test_refuses_to_start_without_token(self, monkeypatch):
        monkeypatch.delenv(bot.BOT_TOKEN_ENV_VAR, raising=False)
        with pytest.raises(SystemExit, match=bot.BOT_TOKEN_ENV_VAR):
            bot.run()

    def test_refuses_to_start_without_allowlist(self, monkeypatch):
        monkeypatch.setenv(bot.BOT_TOKEN_ENV_VAR, "fake-token")
        monkeypatch.delenv(bot.ALLOWED_USERS_ENV_VAR, raising=False)
        with pytest.raises(SystemExit, match=bot.ALLOWED_USERS_ENV_VAR):
            bot.run()


class TestPollOnce:
    def test_dispatches_updates_and_advances_offset(self, monkeypatch):
        client = MagicMock()
        client.get_updates.return_value = [
            {"update_id": 5, "message": {"chat": {"id": 1}, "from": {"id": 9}, "text": "/start"}},
        ]

        next_offset = bot.poll_once(client, offset=None, allowed_user_ids={9})

        assert next_offset == 6
        client.get_updates.assert_called_once_with(offset=None, timeout=bot.POLL_TIMEOUT_SECONDS)
        client.send_message.assert_called_once()
        sent_chat_id, sent_text = client.send_message.call_args[0]
        assert sent_chat_id == 1
        assert "notebooklm" in sent_text.lower() or "NotebookLM" in sent_text

    def test_no_updates_keeps_offset(self, monkeypatch):
        client = MagicMock()
        client.get_updates.return_value = []

        next_offset = bot.poll_once(client, offset=10, allowed_user_ids={9})

        assert next_offset == 10

    def test_send_failure_does_not_raise(self, monkeypatch):
        client = MagicMock()
        client.get_updates.return_value = [
            {"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": 9}, "text": "/start"}},
        ]
        client.send_message.side_effect = ConnectionError("boom")

        # Should not raise even though delivery fails.
        bot.poll_once(client, offset=None, allowed_user_ids={9})
