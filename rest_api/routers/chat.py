"""Chat/ask endpoint. Answers carry the provenance marker (see services/provenance.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from notebooklm_tools.services.chat import query as chat_query

from ..client_pool import DEFAULT_PROFILE
from ..deps import get_notebooklm_client, require_api_key

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_api_key)])


class AskRequest(BaseModel):
    profile: str = Field(default=DEFAULT_PROFILE, description="Auth profile / account to use")
    notebook_id: str
    question: str
    source_ids: list[str] | None = None
    conversation_id: str | None = Field(
        default=None, description="Pass a previous response's conversation_id for follow-ups"
    )
    timeout: float | None = None


@router.post("/ask")
async def ask(body: AskRequest) -> dict:
    client = get_notebooklm_client(body.profile)
    result = chat_query(
        client,
        body.notebook_id,
        body.question,
        source_ids=body.source_ids,
        conversation_id=body.conversation_id,
        timeout=body.timeout,
    )
    return {"success": True, "data": result}
