"""End-to-end REST API route tests (TestClient, no real NotebookLM/network calls)."""

import pytest
from fastapi.testclient import TestClient

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.core.client import NotebookLMClient
from rest_api import deps
from rest_api.main import app

API_KEY = "test-key-123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(deps.API_KEYS_ENV_VAR, API_KEY)
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": API_KEY}


def _make_profile(name: str = "default") -> None:
    """Save a dummy profile so client_pool can build a NotebookLMClient."""
    AuthManager(name).save_profile(
        cookies={"SID": "x", "HSID": "x", "SSID": "x", "APISID": "x", "SAPISID": "x"},
        csrf_token="csrf",
        session_id="sess",
        email="fake@example.com",
    )


class TestHealth:
    def test_health_is_unauthenticated(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"success": True, "status": "ok"}


class TestApiKeyGuard:
    def test_missing_key_is_401(self, client):
        r = client.get("/notebooks")
        assert r.status_code == 401

    def test_wrong_key_is_403(self, client):
        r = client.get("/notebooks", headers={"X-API-Key": "nope"})
        assert r.status_code == 403

    def test_every_router_requires_a_key(self, client):
        for method, path, json_body in [
            ("GET", "/notebooks", None),
            ("GET", "/notebooks/nb-1", None),
            ("POST", "/chat/ask", {"notebook_id": "nb-1", "question": "hi"}),
            ("POST", "/sources", {"notebook_id": "nb-1", "source_type": "text", "text": "hi"}),
            (
                "POST",
                "/studio/generate",
                {"notebook_id": "nb-1", "artifact_type": "audio"},
            ),
            ("GET", "/studio/status/nb-1", None),
        ]:
            r = client.request(method, path, json=json_body)
            assert r.status_code == 401, f"{method} {path} did not require auth"


class TestNoProfileConfigured:
    def test_list_notebooks_without_saved_credentials_is_404(self, client, auth_headers):
        r = client.get("/notebooks", headers=auth_headers)
        assert r.status_code == 404
        assert "default" in r.json()["detail"]


class TestNotebooksRoute:
    def test_list_notebooks_with_profile_returns_success_envelope(
        self, client, auth_headers, monkeypatch
    ):
        _make_profile()
        monkeypatch.setattr(NotebookLMClient, "list_notebooks", lambda self, debug=False: [])

        r = client.get("/notebooks", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["data"]["count"] == 0
        assert body["data"]["notebooks"] == []
