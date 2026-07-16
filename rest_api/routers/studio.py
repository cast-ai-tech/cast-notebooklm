"""Studio artifact generation endpoints.

Covers all 9 artifact types (audio, video, infographic, slide_deck, report,
flashcards, quiz, data_table, mind_map) through the same unified
`create_artifact` service function the CLI's `nlm studio create` and the
MCP `studio_create` tool already use -- see
notebooklm_tools/services/studio.py for the full set of per-type keyword
options (audio_format, video_format, slide_format, question_count, etc.),
all accepted here through `options`.

Also adds two capabilities not present in any of the three upstream
projects this repo is built on:
- `/studio/content-pack`: generate a curated bundle of artifact types in
  one call, instead of one request per type.
- `webhook_url` on both `/studio/generate` and `/studio/content-pack`:
  since Studio generation is asynchronous on Google's side, an optional
  webhook lets a caller (e.g. an n8n workflow) get notified on completion
  instead of polling `/studio/status`. See webhooks.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from notebooklm_tools.services.errors import ServiceError, ValidationError
from notebooklm_tools.services.studio import (
    VALID_ARTIFACT_TYPES,
    create_artifact,
    delete_artifact,
    get_studio_status,
)

from ..client_pool import DEFAULT_PROFILE
from ..deps import get_notebooklm_client, require_api_key
from ..webhooks import notify_on_completion, validate_webhook_url

router = APIRouter(prefix="/studio", tags=["studio"], dependencies=[Depends(require_api_key)])

# Fast default combo for /content-pack: skips video, which takes much
# longer to generate than the rest. Callers can ask for "video" explicitly.
CONTENT_PACK_DEFAULT_TYPES = ["audio", "quiz", "report"]


class GenerateRequest(BaseModel):
    profile: str = Field(default=DEFAULT_PROFILE, description="Auth profile / account to use")
    notebook_id: str
    artifact_type: str = Field(description=f"One of: {', '.join(sorted(VALID_ARTIFACT_TYPES))}")
    source_ids: list[str] | None = None
    options: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Per-type keyword options passed straight through to "
            "notebooklm_tools.services.studio.create_artifact, e.g. "
            '{"audio_format": "deep_dive"} or {"question_count": 5}.'
        ),
    )
    webhook_url: str | None = Field(
        default=None,
        description=(
            "If set, POSTed once with a completion summary when this artifact "
            "finishes generating (or times out after 20 minutes)."
        ),
    )


@router.post("/generate")
async def generate(body: GenerateRequest) -> dict:
    if body.webhook_url:
        validate_webhook_url(body.webhook_url)
    client = get_notebooklm_client(body.profile)
    result = create_artifact(
        client,
        body.notebook_id,
        body.artifact_type,
        source_ids=body.source_ids,
        **body.options,
    )
    artifact_id = result.get("artifact_id")
    if body.webhook_url and artifact_id:
        notify_on_completion(client, body.notebook_id, [artifact_id], body.webhook_url)
    return {"success": True, "data": result}


class ContentPackRequest(BaseModel):
    profile: str = Field(default=DEFAULT_PROFILE, description="Auth profile / account to use")
    notebook_id: str
    source_ids: list[str] | None = None
    types: list[str] = Field(
        default_factory=lambda: list(CONTENT_PACK_DEFAULT_TYPES),
        description=(
            "Which Studio artifact types to generate together. Default is a fast "
            "combo (audio + quiz + report) that skips video, which takes much "
            "longer than the rest. Add 'video' explicitly to include it."
        ),
    )
    options: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-type keyword options, keyed by artifact type, e.g. "
            '{"audio": {"audio_format": "deep_dive"}, "quiz": {"question_count": 5}}.'
        ),
    )
    webhook_url: str | None = Field(
        default=None,
        description=(
            "If set, POSTed once with a completion summary when every artifact in "
            "the pack finishes generating (or times out after 20 minutes)."
        ),
    )


@router.post("/content-pack")
async def content_pack(body: ContentPackRequest) -> dict:
    """Generate several Studio artifact types for one notebook in a single call.

    Each type is requested independently; one type failing (e.g. an invalid
    option) does not stop the rest -- the response reports per-type success.
    """
    if body.webhook_url:
        validate_webhook_url(body.webhook_url)
    client = get_notebooklm_client(body.profile)

    results: list[dict[str, Any]] = []
    artifact_ids: list[str] = []
    for artifact_type in body.types:
        try:
            result = create_artifact(
                client,
                body.notebook_id,
                artifact_type,
                source_ids=body.source_ids,
                **body.options.get(artifact_type, {}),
            )
            results.append({"artifact_type": artifact_type, "success": True, "data": result})
            artifact_id = result.get("artifact_id")
            if artifact_id:
                artifact_ids.append(artifact_id)
        except (ValidationError, ServiceError) as e:
            results.append(
                {"artifact_type": artifact_type, "success": False, "error": e.user_message}
            )

    if body.webhook_url and artifact_ids:
        notify_on_completion(client, body.notebook_id, artifact_ids, body.webhook_url)

    return {"success": True, "data": {"notebook_id": body.notebook_id, "results": results}}


@router.get("/status/{notebook_id}")
async def status(
    notebook_id: str,
    profile: str = DEFAULT_PROFILE,
    artifact_id: str | None = None,
) -> dict:
    """Status of every studio artifact in the notebook.

    Pass `artifact_id` to filter the result down to a single artifact.
    """
    client = get_notebooklm_client(profile)
    result = get_studio_status(client, notebook_id)
    if artifact_id:
        result = {
            **result,
            "artifacts": [a for a in result["artifacts"] if a.get("artifact_id") == artifact_id],
        }
    return {"success": True, "data": result}


class DeleteRequest(BaseModel):
    profile: str = Field(default=DEFAULT_PROFILE, description="Auth profile / account to use")
    notebook_id: str
    artifact_id: str


@router.post("/delete")
async def delete(body: DeleteRequest) -> dict:
    client = get_notebooklm_client(body.profile)
    delete_artifact(client, body.artifact_id, body.notebook_id)
    return {"success": True, "data": {"artifact_id": body.artifact_id, "deleted": True}}
