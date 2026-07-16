"""Tests for POST /studio/content-pack."""

import pytest
from fastapi.testclient import TestClient

from notebooklm_tools.core.auth import AuthManager
from notebooklm_tools.services.errors import ValidationError
from rest_api import deps
from rest_api.main import app
from rest_api.routers import studio as studio_router

API_KEY = "test-key-123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(deps.API_KEYS_ENV_VAR, API_KEY)
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": API_KEY}


@pytest.fixture
def with_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTEBOOKLM_MCP_CLI_PATH", str(tmp_path / "storage"))
    AuthManager("default").save_profile(
        cookies={"SID": "x", "HSID": "x", "SSID": "x", "APISID": "x", "SAPISID": "x"},
        csrf_token="csrf",
        session_id="sess",
        email="fake@example.com",
    )


def test_content_pack_defaults_to_audio_quiz_report(client, auth_headers, with_profile, monkeypatch):
    calls = []

    def fake_create_artifact(client_, notebook_id, artifact_type, *, source_ids=None, **options):
        calls.append(artifact_type)
        return {"artifact_type": artifact_type, "artifact_id": f"art-{artifact_type}", "status": "in_progress"}

    monkeypatch.setattr(studio_router, "create_artifact", fake_create_artifact)

    r = client.post(
        "/studio/content-pack",
        headers=auth_headers,
        json={"notebook_id": "nb-1"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert calls == ["audio", "quiz", "report"]
    results = body["data"]["results"]
    assert len(results) == 3
    assert all(item["success"] for item in results)


def test_content_pack_custom_types_and_per_type_options(client, auth_headers, with_profile, monkeypatch):
    seen_options = {}

    def fake_create_artifact(client_, notebook_id, artifact_type, *, source_ids=None, **options):
        seen_options[artifact_type] = options
        return {"artifact_type": artifact_type, "artifact_id": f"art-{artifact_type}", "status": "in_progress"}

    monkeypatch.setattr(studio_router, "create_artifact", fake_create_artifact)

    r = client.post(
        "/studio/content-pack",
        headers=auth_headers,
        json={
            "notebook_id": "nb-1",
            "types": ["audio", "video"],
            "options": {"audio": {"audio_format": "deep_dive"}, "video": {"video_format": "explainer"}},
        },
    )

    assert r.status_code == 200
    assert seen_options == {
        "audio": {"audio_format": "deep_dive"},
        "video": {"video_format": "explainer"},
    }


def test_content_pack_one_type_failing_does_not_block_the_rest(
    client, auth_headers, with_profile, monkeypatch
):
    def fake_create_artifact(client_, notebook_id, artifact_type, *, source_ids=None, **options):
        if artifact_type == "quiz":
            raise ValidationError("bad question count", user_message="Question count must be positive.")
        return {"artifact_type": artifact_type, "artifact_id": f"art-{artifact_type}", "status": "in_progress"}

    monkeypatch.setattr(studio_router, "create_artifact", fake_create_artifact)

    r = client.post(
        "/studio/content-pack",
        headers=auth_headers,
        json={"notebook_id": "nb-1"},
    )

    assert r.status_code == 200
    results = {item["artifact_type"]: item for item in r.json()["data"]["results"]}
    assert results["audio"]["success"] is True
    assert results["report"]["success"] is True
    assert results["quiz"]["success"] is False
    assert results["quiz"]["error"] == "Question count must be positive."


def test_content_pack_triggers_webhook_with_all_artifact_ids(
    client, auth_headers, with_profile, monkeypatch
):
    notified = {}

    def fake_create_artifact(client_, notebook_id, artifact_type, *, source_ids=None, **options):
        return {"artifact_type": artifact_type, "artifact_id": f"art-{artifact_type}", "status": "in_progress"}

    def fake_notify(client_, notebook_id, artifact_ids, webhook_url):
        notified["notebook_id"] = notebook_id
        notified["artifact_ids"] = artifact_ids
        notified["webhook_url"] = webhook_url

    monkeypatch.setattr(studio_router, "create_artifact", fake_create_artifact)
    monkeypatch.setattr(studio_router, "notify_on_completion", fake_notify)
    monkeypatch.setattr(studio_router, "validate_webhook_url", lambda url: None)

    r = client.post(
        "/studio/content-pack",
        headers=auth_headers,
        json={"notebook_id": "nb-1", "webhook_url": "https://example.com/hook"},
    )

    assert r.status_code == 200
    assert notified["notebook_id"] == "nb-1"
    assert set(notified["artifact_ids"]) == {"art-audio", "art-quiz", "art-report"}
    assert notified["webhook_url"] == "https://example.com/hook"


def test_generate_triggers_webhook_for_single_artifact(client, auth_headers, with_profile, monkeypatch):
    notified = {}

    def fake_create_artifact(client_, notebook_id, artifact_type, *, source_ids=None, **options):
        return {"artifact_type": artifact_type, "artifact_id": "art-1", "status": "in_progress"}

    def fake_notify(client_, notebook_id, artifact_ids, webhook_url):
        notified["artifact_ids"] = artifact_ids
        notified["webhook_url"] = webhook_url

    monkeypatch.setattr(studio_router, "create_artifact", fake_create_artifact)
    monkeypatch.setattr(studio_router, "notify_on_completion", fake_notify)
    monkeypatch.setattr(studio_router, "validate_webhook_url", lambda url: None)

    r = client.post(
        "/studio/generate",
        headers=auth_headers,
        json={"notebook_id": "nb-1", "artifact_type": "audio", "webhook_url": "https://example.com/hook"},
    )

    assert r.status_code == 200
    assert notified["artifact_ids"] == ["art-1"]
    assert notified["webhook_url"] == "https://example.com/hook"


def test_generate_rejects_ssrf_webhook_url_before_creating_anything(
    client, auth_headers, with_profile, monkeypatch
):
    from rest_api import webhooks as webhooks_module

    called = {"create_artifact": False}

    def fake_create_artifact(*args, **kwargs):
        called["create_artifact"] = True
        return {"artifact_type": "audio", "artifact_id": "art-1", "status": "in_progress"}

    monkeypatch.setattr(studio_router, "create_artifact", fake_create_artifact)
    monkeypatch.setattr(
        webhooks_module.socket, "getaddrinfo", lambda host, port: [(2, 1, 6, "", ("169.254.169.254", 0))]
    )

    r = client.post(
        "/studio/generate",
        headers=auth_headers,
        json={
            "notebook_id": "nb-1",
            "artifact_type": "audio",
            "webhook_url": "http://cloud-metadata.internal/latest/meta-data",
        },
    )

    assert r.status_code == 400
    assert called["create_artifact"] is False
