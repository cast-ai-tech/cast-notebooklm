"""Notebook listing/detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from notebooklm_tools.services import notebooks as notebooks_service

from ..client_pool import DEFAULT_PROFILE
from ..deps import get_notebooklm_client, require_api_key

router = APIRouter(prefix="/notebooks", tags=["notebooks"], dependencies=[Depends(require_api_key)])


@router.get("")
async def list_notebooks(
    profile: str = Query(default=DEFAULT_PROFILE, description="Auth profile / account to use"),
    max_results: int = Query(default=100, ge=1, le=1000),
) -> dict:
    client = get_notebooklm_client(profile)
    result = notebooks_service.list_notebooks(client, max_results=max_results)
    return {"success": True, "data": result}


@router.get("/{notebook_id}")
async def get_notebook(
    notebook_id: str,
    profile: str = Query(default=DEFAULT_PROFILE, description="Auth profile / account to use"),
) -> dict:
    client = get_notebooklm_client(profile)
    result = notebooks_service.get_notebook(client, notebook_id)
    return {"success": True, "data": result}
