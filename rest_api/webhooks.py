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

import ipaddress
import logging
import socket
import threading
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.services.errors import ValidationError
from notebooklm_tools.services.studio import get_studio_status

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_TIMEOUT_SECONDS = 20 * 60  # Studio generation can take several minutes
_TERMINAL_STATUSES = {"completed", "failed"}


def validate_webhook_url(url: str) -> None:
    """Reject webhook URLs that could be used for SSRF against internal
    services: only http(s) schemes, and only hostnames that resolve
    exclusively to public IP addresses (rejects loopback, link-local,
    private, and other reserved ranges -- e.g. 127.0.0.1, 169.254.169.254
    cloud metadata, 10/8, 192.168/16).

    Raises ValidationError (mapped to HTTP 400 by rest_api/main.py) so
    callers get an immediate, clear rejection. Routers call this before
    doing any work (see routers/studio.py); notify_on_completion also
    calls it as a second line of defense.

    Residual risk: this checks the resolved IP at submission time, not at
    the moment the background thread actually sends the POST (which can be
    up to `timeout` seconds later) -- a DNS-rebinding attacker could in
    theory change the resolution in between. Full protection would mean
    pinning the validated IP and connecting to it directly while still
    presenting the original Host/SNI, which is a lot of extra machinery
    for a self-hosted, single-operator tool; accepted as a proportionate
    tradeoff here rather than something a multi-tenant public service
    would need.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(
            f"Invalid webhook_url scheme {parsed.scheme!r}: only http/https are allowed.",
            user_message="webhook_url must be an http:// or https:// URL.",
        )
    if not parsed.hostname:
        raise ValidationError(
            "webhook_url has no hostname.",
            user_message="webhook_url must include a valid hostname.",
        )

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise ValidationError(
            f"Could not resolve webhook_url hostname {parsed.hostname!r}: {e}",
            user_message=f"Could not resolve host {parsed.hostname!r} for webhook_url.",
        ) from e

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_unspecified:
            raise ValidationError(
                f"webhook_url hostname {parsed.hostname!r} resolves to a non-public address ({ip}).",
                user_message=(
                    "webhook_url must point to a public address -- loopback, private, "
                    "and link-local addresses are not allowed (this prevents the server "
                    "from being used to reach internal services)."
                ),
            )


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
        with httpx.Client(timeout=15.0, follow_redirects=False) as http_client:
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

    Raises ValidationError synchronously if `webhook_url` fails
    validate_webhook_url() -- callers should validate up front (see
    routers/studio.py) so a bad URL is rejected before any work is done;
    this is a second line of defense for direct callers.
    """
    validate_webhook_url(webhook_url)
    thread = threading.Thread(
        target=_poll_and_notify,
        args=(client, notebook_id, artifact_ids, webhook_url),
        kwargs={"poll_interval": poll_interval, "timeout": timeout},
        daemon=True,
    )
    thread.start()
