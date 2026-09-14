"""问数服务：串起「流水线执行 → SSE 推送 → 落库」。

这是接口层与核心算法之间唯一的一层胶水，职责边界刻意收窄：
- 负责准备运行时依赖（仓储、LLM）与状态初值；
- 负责把流水线事件翻译成 SSE / 聚合结果；
- 负责把一次问数的过程与结果持久化，供「日志」和「反馈校对」使用。
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.core.log import get_logger
from app.db.session import Database
from app.entities import MetaSnapshot
from app.repositories.dw_repository import DwRepository
from app.repositories.meta_repository import MetaRepository
from app.services.log_service import LogService
from app.services.session_service import SessionService
from app.text2sql.graph import pipeline
from app.text2sql.llm import build_llm
from app.text2sql.state import PipelineContext

logger = get_logger(__name__)


class QueryService:
    def __init__(self, database: Database, session_service: SessionService | None = None,
                 log_service: LogService | None = None) -> None:
        self.database = database
        self.sessions = session_service or SessionService(database.session_factory)
        self.logs = log_service or LogService(database.session_factory)

    # ------------------------------------------------------------ 核心入口

    async def run(self, question: str, provider: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """执行一次问数，逐个 yield 事件。"""
        logger.info("收到问数请求：%s", question)
        snapshot = await self._load_snapshot()
        state: dict[str, Any] = {
            "query": question,
            "token_usage": 0,
            "warnings": [],
            "correction_attempts": 0,
            "error": None,
        }
        async with self.database.session() as session:
            context = PipelineContext(
                meta_repository=MetaRepository(session),
                dw_repository=DwRepository(session),
                llm=build_llm(provider),
                snapshot=snapshot,
                provider=provider or settings.llm_provider,
                max_correction_retry=settings.sql_max_correction_retry,
                row_limit=settings.sql_row_limit,
            )
            async for event in pipeline.run(state, context):
                yield event
        # 流水线结束后统一把可回传的字段整理成一个 state 事件，供上层聚合/落库
        yield {"type": "state", "state": _state_out(state)}

    async def stream(
        self, question: str, session_id: int | None = None, user_name: str = "管理员"
    ) -> AsyncIterator[str]:
        """SSE 流：先建/取会话并把用户消息落库，然后转发流水线事件，最后保存 AI 回复与日志。"""
        started = time.perf_counter()
        session = await self.sessions.ensure_session(session_id, question, user_name)
        await self.sessions.append_message(session["id"], "user", question)
        yield _sse({"type": "session", "session": session})

        steps: list[dict[str, str]] = []
        state_out: dict[str, Any] = {}
        try:
            async for event in self.run(question):
                if event.get("type") == "progress":
                    steps = _merge_step(steps, event)
                elif event.get("type") == "state":
                    state_out = event.get("state", {})
                    continue
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001 - 兜底，保证前端一定能收到错误
            logger.exception("问数执行失败")
            yield _sse({"type": "error", "message": str(exc)})
            state_out = {"error": str(exc)}

        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = _build_payload(question, steps, state_out, duration_ms)
        await self.sessions.append_message(session["id"], "assistant", payload.get("answer", ""), payload)
        await self.logs.add_log(session_id=session["id"], payload=payload, duration_ms=duration_ms)
        yield _sse({"type": "done", "message": payload, "session_id": session["id"]})

    async def query_once(self, question: str) -> dict[str, Any]:
        """同步聚合执行（不落库），用于接口测试与脚本调用。"""
        started = time.perf_counter()
        steps: list[dict[str, str]] = []
        state_out: dict[str, Any] = {}
        try:
            async for event in self.run(question):
                if event.get("type") == "progress":
                    steps = _merge_step(steps, event)
                elif event.get("type") == "state":
                    state_out = event.get("state", {})
        except Exception as exc:  # noqa: BLE001
            state_out = {"error": str(exc)}
        return _build_payload(question, steps, state_out, int((time.perf_counter() - started) * 1000))

    # ------------------------------------------------------------ 内部

    async def _load_snapshot(self) -> MetaSnapshot:
        async with self.database.session() as session:
            return await MetaRepository(session).snapshot()


def _merge_step(steps: list[dict[str, str]], event: dict[str, Any]) -> list[dict[str, str]]:
    label = event.get("step", "")
    for step in steps:
        if step["label"] == label:
            step["status"] = event.get("status", "")
            return steps
    steps.append({"label": label, "node": event.get("node", ""), "status": event.get("status", "")})
    return steps


def _state_out(state: dict[str, Any]) -> dict[str, Any]:
    """从内部 state 中挑出可以回传前端/落库的字段。"""
    result = state.get("result")
    return {
        "sql": state.get("sql", ""),
        "provider": (state.get("generation_meta") or {}).get("provider", ""),
        "generation": state.get("generation_meta") or {},
        "selected_tables": state.get("selected_tables") or [],
        "metric_infos": state.get("metric_infos") or [],
        "value_infos": state.get("value_infos") or [],
        "keywords": state.get("keywords") or [],
        "date_info": state.get("date_info") or {},
        "db_info": state.get("db_info") or {},
        "examples": state.get("examples") or [],
        "chart": state.get("chart"),
        "stats": state.get("stats") or {},
        "answer": state.get("answer") or "",
        "followups": state.get("followups") or [],
        "columns": list(result.columns) if result else [],
        "rows": result.rows[:200] if result else [],
        "row_count": result.row_count if result else 0,
        "error": state.get("error"),
        "warnings": state.get("warnings") or [],
        "token_usage": state.get("token_usage") or 0,
    }


def _build_payload(
    question: str, steps: list[dict[str, str]], state_out: dict[str, Any], duration_ms: int
) -> dict[str, Any]:
    return {
        "question": question,
        "steps": steps,
        "duration_ms": duration_ms,
        **state_out,
    }


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
