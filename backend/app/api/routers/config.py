"""应用配置接口：对应 demo 的「系统管理 → 应用配置」。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_config_service, get_model_service
from app.schemas import ApiResponse, AppConfigPatch
from app.services.config_service import ConfigService
from app.services.model_service import ModelService

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/app", summary="读取应用配置")
async def get_app_config(
    service: Annotated[ConfigService, Depends(get_config_service)],
) -> ApiResponse:
    return ApiResponse.ok(await service.get_app_config())


@router.patch("/app", summary="更新应用配置（局部更新）")
async def patch_app_config(
    payload: AppConfigPatch,
    service: Annotated[ConfigService, Depends(get_config_service)],
) -> ApiResponse:
    return ApiResponse.ok(await service.save_app_config(payload.model_dump(exclude_none=True)))


@router.get("/runtime", summary="当前后端真实生效的运行配置")
async def runtime_config(
    model_service: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse:
    """把「页面上的模型选择」与「后端真正在用的模型」区分清楚，避免误判。"""
    from app.core.config import settings

    return ApiResponse.ok(
        {
            "model": model_service.runtime_model(),
            "sql": {
                "row_limit": settings.sql_row_limit,
                "timeout_seconds": settings.sql_timeout_seconds,
                "max_correction_retry": settings.sql_max_correction_retry,
            },
            "recall": {
                "top_k": settings.recall_top_k,
                "max_tables": settings.recall_max_tables,
            },
        }
    )
