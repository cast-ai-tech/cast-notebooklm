"""Tests for the Studio-completion webhook notifier (rest_api/webhooks.py)."""

import time
from unittest.mock import MagicMock

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

    webhooks.notify_on_completion(MagicMock(), "nb-1", ["art-1"], "https://example.com/webhook")

    # Give the daemon thread a moment to run.
    for _ in range(50):
        if started["called"]:
            break
        time.sleep(0.01)

    assert started["called"] is True
