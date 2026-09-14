"""问数接口：SSE 流式 + 同步聚合两种调用方式。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.deps import get_query_service
from app.schemas import ApiResponse, ChatRequest
from app.services.query_service import QueryService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream", summary="流式问数（SSE）")
async def chat_stream(
    payload: ChatRequest,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> StreamingResponse:
    """以 SSE 持续推送：会话信息 → 各节点进度 → SQL → 结果 → 图表 → 结论。"""
    return StreamingResponse(
        service.stream(payload.question, payload.session_id, payload.user_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 关闭 nginx 缓冲，否则流式会被攒成一次性返回
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/query", summary="同步问数（一次返回完整结果）")
async def chat_query(
    payload: ChatRequest,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> ApiResponse:
    """不落库、不流式，适合脚本、接口测试与第三方集成。"""
    return ApiResponse.ok(await service.query_once(payload.question))
