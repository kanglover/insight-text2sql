"""会话接口：对应 demo 的左侧「近 30 天记录」与快捷提问面板。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_config_service, get_session_service
from app.schemas import (
    ApiResponse,
    SessionCreateRequest,
    SessionRenameRequest,
)
from app.services.config_service import ConfigService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", summary="会话列表")
async def list_sessions(
    service: Annotated[SessionService, Depends(get_session_service)],
    days: int = Query(default=30, ge=0, le=3650, description="0 表示不限时间"),
    keyword: str = "",
) -> ApiResponse:
    return ApiResponse.ok(await service.list_sessions(days=days, keyword=keyword))


@router.get("/quick-questions", summary="快捷提问（常问 / 收藏 / 推荐）")
async def quick_questions(
    service: Annotated[ConfigService, Depends(get_config_service)],
) -> ApiResponse:
    return ApiResponse.ok(await service.quick_questions())


@router.post("", summary="新建会话")
async def create_session(
    payload: SessionCreateRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    return ApiResponse.ok(await service.create(payload.title, payload.user_name))


@router.get("/{session_id}", summary="会话详情（含消息）")
async def get_session(
    session_id: int,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    data = await service.get(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ApiResponse.ok(data)


@router.put("/{session_id}/title", summary="重命名会话")
async def rename_session(
    session_id: int,
    payload: SessionRenameRequest,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    if not await service.rename(session_id, payload.title):
        raise HTTPException(status_code=404, detail="会话不存在")
    return ApiResponse.ok(await service.get(session_id))


@router.post("/{session_id}/pin", summary="置顶 / 取消置顶")
async def pin_session(
    session_id: int,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    pinned = await service.toggle_pin(session_id)
    if pinned is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ApiResponse.ok({"pinned": pinned})


@router.delete("/{session_id}", summary="删除会话")
async def delete_session(
    session_id: int,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    if not await service.delete(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return ApiResponse.ok({"deleted": True})


@router.delete("/{session_id}/messages", summary="清空会话消息")
async def clear_messages(
    session_id: int,
    service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    if not await service.clear_messages(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return ApiResponse.ok({"cleared": True})


@router.post("/favorites", summary="收藏 / 取消收藏一个问题")
async def toggle_favorite(
    service: Annotated[ConfigService, Depends(get_config_service)],
    question: str = Query(min_length=1, max_length=200),
) -> ApiResponse:
    return ApiResponse.ok({"favorites": await service.toggle_favorite(question)})
