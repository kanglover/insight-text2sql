"""反馈接口：对应 demo 的「反馈管理 → 回复校对」。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_feedback_service, get_session_service
from app.schemas import ApiResponse, FeedbackCreateRequest, FeedbackUpdateRequest
from app.services.feedback_service import FeedbackService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.get("", summary="反馈列表（分页 / 搜索 / 状态筛选）")
async def list_feedback(
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
    status: str = Query(default="all", pattern="^(all|待处理|已处理)$"),
    keyword: str = "",
    user_keyword: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ApiResponse:
    return ApiResponse.ok(
        await service.list(
            status=status,
            keyword=keyword,
            user_keyword=user_keyword,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/stats", summary="反馈统计")
async def feedback_stats(
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
) -> ApiResponse:
    return ApiResponse.ok(await service.stats())


@router.post("", summary="提交反馈（用户点「数据有误」）")
async def create_feedback(
    payload: FeedbackCreateRequest,
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    created = await service.create(
        session_id=payload.session_id,
        question=payload.question,
        user_name=payload.user_name,
        message=payload.message,
        ai_reply=payload.ai_reply,
    )
    if payload.session_id:
        await session_service.set_feedback(payload.session_id, user_feedback="数据有误")
    return ApiResponse.ok(created)


@router.put("/{feedback_id}", summary="处理反馈（状态 + 备注）")
async def update_feedback(
    feedback_id: int,
    payload: FeedbackUpdateRequest,
    service: Annotated[FeedbackService, Depends(get_feedback_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
) -> ApiResponse:
    updated = await service.update(feedback_id, status=payload.status, remark=payload.remark)
    if updated is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if payload.status == "已处理" and updated["session_id"]:
        await session_service.set_feedback(updated["session_id"], admin_feedback="已处理")
    return ApiResponse.ok(updated)
