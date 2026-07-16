"""Tests for REST API auth (deps.py)."""

import pytest
from fastapi import HTTPException

from rest_api import deps


def _clear_keys(monkeypatch):
    monkeypatch.delenv(deps.API_KEYS_ENV_VAR, raising=False)


class TestGetConfiguredApiKeys:
    def test_empty_when_unset(self, monkeypatch):
        _clear_keys(monkeypatch)
        assert deps.get_configured_api_keys() == set()

    def test_parses_comma_separated_list(self, monkeypatch):
        monkeypatch.setenv(deps.API_KEYS_ENV_VAR, "abc, def ,ghi")
        assert deps.get_configured_api_keys() == {"abc", "def", "ghi"}


class TestRequireApiKey:
    @pytest.mark.asyncio
    async def test_missing_header_raises_401(self, monkeypatch):
        _clear_keys(monkeypatch)
        monkeypatch.setenv(deps.API_KEYS_ENV_VAR, "secret")

        with pytest.raises(HTTPException) as exc_info:
            await deps.require_api_key(x_api_key=None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_raises_403(self, monkeypatch):
        _clear_keys(monkeypatch)
        monkeypatch.setenv(deps.API_KEYS_ENV_VAR, "secret")

        with pytest.raises(HTTPException) as exc_info:
            await deps.require_api_key(x_api_key="not-secret")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_correct_key_passes(self, monkeypatch):
        _clear_keys(monkeypatch)
        monkeypatch.setenv(deps.API_KEYS_ENV_VAR, "secret,other")

        result = await deps.require_api_key(x_api_key="other")
        assert result == "other"


class TestGetNotebooklmClient:
    def test_missing_profile_raises_404(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NOTEBOOKLM_MCP_CLI_PATH", str(tmp_path / "storage"))

        with pytest.raises(HTTPException) as exc_info:
            deps.get_notebooklm_client("no-such-profile")
        assert exc_info.value.status_code == 404
