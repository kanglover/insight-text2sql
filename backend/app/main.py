"""FastAPI 应用入口。

启动时：
1. 建表（幂等）；
2. 如果元数据库为空，则自动灌入数仓与元数据种子 —— 让 `docker compose up` / `make dev`
   之后立刻就能问数，不需要额外手工步骤。
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import chat, config, feedback, models, sessions, system
from app.core.config import settings
from app.core.log import get_logger, request_id_ctx, setup_logging
from app.db.session import db

logger = get_logger(__name__)


async def _bootstrap() -> None:
    """建表 + 首次自动灌数据。"""
    from sqlalchemy import func, select

    from app.models.meta import MetaTable

    await db.create_all()
    await db.migrate()
    async with db.session() as session:
        count = (
            await session.execute(select(func.count(MetaTable.id)))
        ).scalar_one()
    if count == 0:
        from app.data.seed import seed_database

        logger.info("检测到元数据为空，开始灌入自制数仓与元数据知识库 …")
        counts = await seed_database(db, reset=True)
        logger.info(
            "种子数据写入完成：事实表 %s 行 / 维表 %s 行 / 元数据 %s 行",
            counts.get("dw_fact_revenue", 0),
            counts.get("dw_dim_org", 0),
            counts.get("meta_column", 0),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging("DEBUG" if settings.debug else "INFO")
    logger.info("%s 启动中 …", settings.app_name)
    await _bootstrap()
    yield
    await db.dispose()
    logger.info("服务已关闭")


app = FastAPI(
    title=settings.app_name,
    description="销售经管场景的 Text2SQL 问数后端：检索增强 → SQL 生成 → 安全校验 → 执行 → 解读",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    system.router,
    chat.router,
    sessions.router,
    feedback.router,
    config.router,
    models.router,
):
    app.include_router(router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id_ctx.set(str(uuid.uuid4())[:8])
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id_ctx.get()
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常：%s", exc)
    return JSONResponse(status_code=500, content={"code": 500, "message": str(exc), "data": None})


@app.get("/", include_in_schema=False)
async def index() -> dict:
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/api/health",
        "chat": "POST /api/chat/stream",
    }
