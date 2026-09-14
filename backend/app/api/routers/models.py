"""模型配置接口：对应 demo 的「系统管理 → 模型配置」。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_model_service
from app.schemas import ApiResponse, ModelAddRequest, ModelTestRequest
from app.services.model_service import ModelService

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", summary="模型清单")
async def list_models(
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse:
    return ApiResponse.ok(await service.list_models())


@router.post("/select", summary="选择并保存当前模型")
async def select_model(
    model_id: int,
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse:
    result = await service.select(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    return ApiResponse.ok(result)


@router.post("", summary="新增模型")
async def add_model(
    payload: ModelAddRequest,
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse:
    return ApiResponse.ok(
        await service.add_model(
            base_url=payload.base_url,
            model_name=payload.model_name,
            api_key=payload.api_key,
            name=payload.name,
        )
    )


@router.delete("/{model_id}", summary="删除模型")
async def delete_model(
    model_id: int,
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse:
    if not await service.delete_model(model_id):
        raise HTTPException(status_code=404, detail="模型不存在")
    return ApiResponse.ok({"deleted": True})


@router.post("/test", summary="测试模型连通性")
async def test_model(
    payload: ModelTestRequest,
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ApiResponse:
    return ApiResponse.ok(
        await service.test_connection(
            base_url=payload.base_url,
            model_name=payload.model_name,
            api_key=payload.api_key,
        )
    )
