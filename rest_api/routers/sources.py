"""Source management endpoint (url/text/drive/file)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from notebooklm_tools.services.sources import add_source

from ..client_pool import DEFAULT_PROFILE
from ..deps import get_notebooklm_client, require_api_key

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(require_api_key)])


class AddSourceRequest(BaseModel):
    profile: str = Field(default=DEFAULT_PROFILE, description="Auth profile / account to use")
    notebook_id: str
    source_type: str = Field(description="One of: url, text, drive, file")
    url: str | None = None
    text: str | None = None
    title: str | None = None
    file_path: str | None = Field(
        default=None,
        description=(
            "Path on the REST API server's filesystem (source_type='file'). "
            "This endpoint does not accept file uploads."
        ),
    )
    document_id: str | None = Field(default=None, description="Google Drive document ID")
    doc_type: str = Field(default="doc", description="Drive doc type: doc|slides|sheets|pdf")
    wait: bool = Field(default=False, description="Wait for source processing to finish")
    wait_timeout: float = 120.0


@router.post("")
async def add(body: AddSourceRequest) -> dict:
    client = get_notebooklm_client(body.profile)
    result = add_source(
        client,
        body.notebook_id,
        body.source_type,
        url=body.url,
        text=body.text,
        title=body.title,
        file_path=body.file_path,
        document_id=body.document_id,
        doc_type=body.doc_type,
        wait=body.wait,
        wait_timeout=body.wait_timeout,
    )
    return {"success": True, "data": result}
