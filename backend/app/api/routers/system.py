"""日志与系统信息接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_database, get_log_service
from app.db.session import Database
from app.repositories.meta_repository import MetaRepository
from app.schemas import ApiResponse
from app.services.log_service import LogService
from app.text2sql.graph import pipeline

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", summary="健康检查")
async def health() -> ApiResponse:
    from app.core.config import settings

    return ApiResponse.ok(
        {
            "status": "ok",
            "app": settings.app_name,
            "llm_provider": settings.llm_provider,
            "llm_configured": bool(settings.llm_api_key.strip()),
        }
    )


@router.get("/logs", summary="问数日志")
async def list_logs(
    service: Annotated[LogService, Depends(get_log_service)],
    days: int = Query(default=30, ge=0, le=3650),
    keyword: str = "",
    user_name: str = "",
    limit: int = Query(default=100, ge=1, le=500),
) -> ApiResponse:
    return ApiResponse.ok(
        await service.list_logs(days=days, keyword=keyword, user_name=user_name, limit=limit)
    )


@router.get("/logs/summary", summary="问数日志统计")
async def logs_summary(
    service: Annotated[LogService, Depends(get_log_service)],
    days: int = Query(default=30, ge=1, le=3650),
) -> ApiResponse:
    return ApiResponse.ok(await service.summary(days=days))


@router.get("/pipeline", summary="问数流水线结构（用于前端展示与文档）")
async def pipeline_info() -> ApiResponse:
    nodes = [
        {"name": node.name, "label": node.label} for node in pipeline.nodes.values()
    ]
    return ApiResponse.ok(
        {
            "name": pipeline.name,
            "entry": pipeline.entry,
            "nodes": nodes,
            "mermaid": pipeline.mermaid(),
        }
    )


@router.get("/metadata", summary="数据字典（表 / 字段 / 指标 / 取值）")
async def metadata(
    database: Annotated[Database, Depends(get_database)],
) -> ApiResponse:
    async with database.session() as session:
        snapshot = await MetaRepository(session).snapshot()
    tables = [
        {
            "table_name": table.table_name,
            "comment": table.comment,
            "role": table.role,
            "domain": table.business_domain,
            "columns": [
                {
                    "name": c.column_name,
                    "type": c.data_type,
                    "comment": c.comment,
                    "role": c.role,
                }
                for c in table.columns
            ],
        }
        for table in snapshot.tables
    ]
    return ApiResponse.ok(
        {
            "tables": tables,
            "metrics": [
                {
                    "name": m.metric_name,
                    "aliases": list(m.aliases),
                    "formula": m.formula,
                    "unit": m.unit,
                    "description": m.description,
                }
                for m in snapshot.metrics
            ],
            "examples": [
                {"question": e.question, "sql": e.sql, "intent": e.intent}
                for e in snapshot.examples
            ],
            "value_count": len(snapshot.values),
        }
    )
