"""Tests for the Studio-completion webhook notifier (rest_api/webhooks.py)."""

import time
from unittest.mock import MagicMock

import pytest

from notebooklm_tools.services.errors import ValidationError
from rest_api import webhooks


class _FakeResponse:
    def raise_for_status(self):
        pass


def test_notify_on_completion_posts_once_artifact_completes(monkeypatch):
    calls = {"status_polls": 0, "posted": None}

    def fake_get_studio_status(client, notebook_id):
        calls["status_polls"] += 1
        status = "completed" if calls["status_polls"] >= 2 else "in_progress"
        return {"artifacts": [{"artifact_id": "art-1", "status": status, "type": "audio"}]}

    def fake_post(self, url, json):
        calls["posted"] = (url, json)
        return _FakeResponse()

    monkeypatch.setattr(webhooks, "get_studio_status", fake_get_studio_status)
    monkeypatch.setattr(webhooks.httpx.Client, "post", fake_post)
    monkeypatch.setattr(webhooks.time, "sleep", lambda _seconds: None)

    webhooks._poll_and_notify(
        MagicMock(),
        "nb-1",
        ["art-1"],
        "https://example.com/webhook",
        poll_interval=0.01,
        timeout=5,
    )

    assert calls["status_polls"] == 2
    url, payload = calls["posted"]
    assert url == "https://example.com/webhook"
    assert payload["event"] == "studio.completed"
    assert payload["notebook_id"] == "nb-1"
    assert payload["artifacts"][0]["artifact_id"] == "art-1"
    assert payload["timed_out_artifact_ids"] == []


def test_notify_on_completion_times_out(monkeypatch):
    calls = {"posted": None}

    def fake_get_studio_status(client, notebook_id):
        return {"artifacts": [{"artifact_id": "art-1", "status": "in_progress"}]}

    def fake_post(self, url, json):
        calls["posted"] = (url, json)
        return _FakeResponse()

    fake_time = {"now": 0.0}

    def fake_monotonic():
        return fake_time["now"]

    def fake_sleep(seconds):
        fake_time["now"] += seconds

    monkeypatch.setattr(webhooks, "get_studio_status", fake_get_studio_status)
    monkeypatch.setattr(webhooks.httpx.Client, "post", fake_post)
    monkeypatch.setattr(webhooks.time, "sleep", fake_sleep)
    monkeypatch.setattr(webhooks.time, "monotonic", fake_monotonic)

    webhooks._poll_and_notify(
        MagicMock(),
        "nb-1",
        ["art-1"],
        "https://example.com/webhook",
        poll_interval=1,
        timeout=3,
    )

    url, payload = calls["posted"]
    assert payload["event"] == "studio.timeout"
    assert payload["timed_out_artifact_ids"] == ["art-1"]
    assert payload["artifacts"] == []


def test_notify_on_completion_swallows_delivery_errors(monkeypatch):
    def fake_get_studio_status(client, notebook_id):
        return {"artifacts": [{"artifact_id": "art-1", "status": "completed"}]}

    def fake_post(self, url, json):
        raise ConnectionError("boom")

    monkeypatch.setattr(webhooks, "get_studio_status", fake_get_studio_status)
    monkeypatch.setattr(webhooks.httpx.Client, "post", fake_post)
    monkeypatch.setattr(webhooks.time, "sleep", lambda _seconds: None)

    # Should not raise even though the POST fails.
    webhooks._poll_and_notify(
        MagicMock(), "nb-1", ["art-1"], "https://example.com/webhook", poll_interval=0.01, timeout=5
    )


def test_notify_on_completion_starts_a_background_thread(monkeypatch):
    started = {"called": False}

    def fake_poll_and_notify(*args, **kwargs):
        started["called"] = True

    monkeypatch.setattr(webhooks, "_poll_and_notify", fake_poll_and_notify)
    monkeypatch.setattr(webhooks, "validate_webhook_url", lambda url: None)

    webhooks.notify_on_completion(MagicMock(), "nb-1", ["art-1"], "https://example.com/webhook")

    # Give the daemon thread a moment to run.
    for _ in range(50):
        if started["called"]:
            break
        time.sleep(0.01)

    assert started["called"] is True


def test_notify_on_completion_rejects_invalid_url_before_starting_thread(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("_poll_and_notify should not run for an invalid webhook_url")

    monkeypatch.setattr(webhooks, "_poll_and_notify", fail_if_called)

    with pytest.raises(ValidationError):
        webhooks.notify_on_completion(MagicMock(), "nb-1", ["art-1"], "ftp://example.com/webhook")


class TestValidateWebhookUrl:
    def _mock_public_dns(self, monkeypatch, ip="93.184.216.34"):
        monkeypatch.setattr(
            webhooks.socket,
            "getaddrinfo",
            lambda host, port: [(2, 1, 6, "", (ip, 0))],
        )

    def _mock_private_dns(self, monkeypatch, ip):
        monkeypatch.setattr(
            webhooks.socket,
            "getaddrinfo",
            lambda host, port: [(2, 1, 6, "", (ip, 0))],
        )

    def test_accepts_url_resolving_to_public_ip(self, monkeypatch):
        self._mock_public_dns(monkeypatch)
        webhooks.validate_webhook_url("https://example.com/webhook")  # should not raise

    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValidationError, match="scheme"):
            webhooks.validate_webhook_url("ftp://example.com/webhook")

    def test_rejects_missing_hostname(self):
        with pytest.raises(ValidationError, match="hostname"):
            webhooks.validate_webhook_url("http:///no-host")

    def test_rejects_unresolvable_hostname(self, monkeypatch):
        def raise_gaierror(host, port):
            raise webhooks.socket.gaierror("nope")

        monkeypatch.setattr(webhooks.socket, "getaddrinfo", raise_gaierror)

        with pytest.raises(ValidationError, match="resolve"):
            webhooks.validate_webhook_url("https://nonexistent.invalid/webhook")

    def test_rejects_loopback(self, monkeypatch):
        self._mock_private_dns(monkeypatch, "127.0.0.1")
        with pytest.raises(ValidationError, match="non-public"):
            webhooks.validate_webhook_url("https://localhost/webhook")

    def test_rejects_cloud_metadata_link_local(self, monkeypatch):
        self._mock_private_dns(monkeypatch, "169.254.169.254")
        with pytest.raises(ValidationError, match="non-public"):
            webhooks.validate_webhook_url("https://metadata.internal/webhook")

    def test_rejects_private_range(self, monkeypatch):
        self._mock_private_dns(monkeypatch, "10.0.0.5")
        with pytest.raises(ValidationError, match="non-public"):
            webhooks.validate_webhook_url("https://internal-service/webhook")

    def test_rejects_private_range_192_168(self, monkeypatch):
        self._mock_private_dns(monkeypatch, "192.168.1.10")
        with pytest.raises(ValidationError, match="non-public"):
            webhooks.validate_webhook_url("https://router.local/webhook")

    def test_rejects_ipv6_loopback(self, monkeypatch):
        monkeypatch.setattr(
            webhooks.socket,
            "getaddrinfo",
            lambda host, port: [(10, 1, 6, "", ("::1", 0, 0, 0))],
        )
        with pytest.raises(ValidationError, match="non-public"):
            webhooks.validate_webhook_url("https://[::1]/webhook")
