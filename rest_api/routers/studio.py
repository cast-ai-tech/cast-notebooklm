"""Studio artifact generation endpoint.

Covers all 9 artifact types (audio, video, infographic, slide_deck, report,
flashcards, quiz, data_table, mind_map) through the same unified
`create_artifact` service function the CLI's `nlm studio create` and the
MCP `studio_create` tool already use -- see
notebooklm_tools/services/studio.py for the full set of per-type keyword
options (audio_format, video_format, slide_format, question_count, etc.),
all accepted here through `options`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from notebooklm_tools.services.studio import (
    VALID_ARTIFACT_TYPES,
    create_artifact,
    delete_artifact,
    get_studio_status,
)

from ..client_pool import DEFAULT_PROFILE
from ..deps import get_notebooklm_client, require_api_key

router = APIRouter(prefix="/studio", tags=["studio"], dependencies=[Depends(require_api_key)])


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


@router.post("/generate")
async def generate(body: GenerateRequest) -> dict:
    client = get_notebooklm_client(body.profile)
    result = create_artifact(
        client,
        body.notebook_id,
        body.artifact_type,
        source_ids=body.source_ids,
        **body.options,
    )
    return {"success": True, "data": result}


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
