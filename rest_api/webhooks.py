"""Webhook notifications for asynchronous Studio artifact completion.

NotebookLM's Studio generation (audio, video, etc.) is asynchronous on
Google's side: creating an artifact only starts the job and returns
immediately with status "in_progress" -- the caller has to poll
notebooklm_tools.services.studio.get_studio_status() to find out when it's
actually done. This module adds an optional push notification on top of
that polling: pass a webhook_url when creating an artifact (or a content
pack, see routers/studio.py) and a background thread polls status for you,
then POSTs a summary to that URL once every requested artifact reaches a
terminal state (completed or failed), or once a timeout is hit.

Not part of any of the three upstream projects this repo is built on --
new capability, added so Studio generation is usable from tools (n8n,
Zapier, Make) that can't hold a request open for the minutes generation
can take.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.services.studio import get_studio_status

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_TIMEOUT_SECONDS = 20 * 60  # Studio generation can take several minutes
_TERMINAL_STATUSES = {"completed", "failed"}


def _poll_and_notify(
    client: NotebookLMClient,
    notebook_id: str,
    artifact_ids: list[str],
    webhook_url: str,
    *,
    poll_interval: float,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    pending = set(artifact_ids)
    results: dict[str, dict[str, Any]] = {}

    while pending and time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            status = get_studio_status(client, notebook_id)
        except Exception as e:
            logger.warning(f"Webhook poll failed for notebook {notebook_id}: {e}")
            continue

        for artifact in status.get("artifacts", []):
            artifact_id = artifact.get("artifact_id")
            if artifact_id in pending and artifact.get("status") in _TERMINAL_STATUSES:
                results[artifact_id] = artifact
                pending.discard(artifact_id)

    payload = {
        "event": "studio.completed" if not pending else "studio.timeout",
        "notebook_id": notebook_id,
        "artifacts": list(results.values()),
        "timed_out_artifact_ids": list(pending),
    }

    try:
        with httpx.Client(timeout=15.0) as http_client:
            response = http_client.post(webhook_url, json=payload)
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"Failed to deliver webhook to {webhook_url}: {e}")


def notify_on_completion(
    client: NotebookLMClient,
    notebook_id: str,
    artifact_ids: list[str],
    webhook_url: str,
    *,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Start a background thread that POSTs to `webhook_url` once every
    artifact in `artifact_ids` reaches a terminal state, or on timeout.

    Fire-and-forget: does not block the caller, and delivery failures are
    only logged (the artifact itself was already created successfully).
    """
    thread = threading.Thread(
        target=_poll_and_notify,
        args=(client, notebook_id, artifact_ids, webhook_url),
        kwargs={"poll_interval": poll_interval, "timeout": timeout},
        daemon=True,
    )
    thread.start()
