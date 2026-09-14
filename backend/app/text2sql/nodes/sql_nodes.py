"""⑧⑨⑩⑪ 生成 → 校验 → 修正 → 执行。"""

import time

from app.core.log import get_logger
from app.text2sql import generators
from app.text2sql.pipeline import Emit
from app.text2sql.sql_guard import guard_sql
from app.text2sql.state import PipelineContext, PipelineState

logger = get_logger(__name__)


async def generate_sql(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    generated = await generators.generate_sql(
        query=state.get("query", ""),
        snapshot=context.snapshot,
        llm=context.llm,
        provider=context.provider,
        tables=state.get("candidate_tables") or [],
        metrics=state.get("metric_infos") or [],
        values=state.get("value_infos") or [],
        date_info=state.get("date_info") or {},
        db_info=state.get("db_info") or {},
        examples=state.get("examples") or [],
        join_paths=state.get("join_paths") or [],
    )
    logger.info("[%s] 生成 SQL：%s", generated.provider, generated.sql.replace("\n", " ")[:400])
    return {
        "raw_sql": generated.sql,
        "sql": generated.sql,
        "provider": generated.provider,
        "error": None,
        "warnings": [],
        "correction_attempts": 0,
        "sql_prompt": generated.prompt,
        "generation_meta": {
            "provider": generated.provider,
            "intent": generated.intent,
            "confidence": generated.confidence,
            "reason": generated.reason,
            "fallback_reason": generated.fallback_reason,
        },
        "token_usage": (state.get("token_usage") or 0) + generated.tokens,
    }


async def validate_sql(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    """静态安全校验 + 交给数据库 EXPLAIN 解析一次。

    校验结果写到 ``state['error']``，由流水线的条件边决定去 run_sql 还是 correct_sql。
    """
    dialect = (state.get("db_info") or {}).get("dialect", "sqlite")
    guarded = guard_sql(
        state.get("sql", ""),
        allowed_tables=context.snapshot.table_names,
        dialect=dialect,
        row_limit=context.row_limit,
    )
    if not guarded.ok:
        emit({"type": "guard", "status": "rejected", "error": guarded.error})
        return {"error": guarded.error, "warnings": []}

    try:
        await context.dw_repository.explain(guarded.sql)
    except Exception as exc:  # noqa: BLE001 - 数据库解析失败也要走修正分支
        message = str(exc)
        emit({"type": "guard", "status": "rejected", "error": message})
        return {"error": message, "warnings": guarded.warnings}

    emit(
        {
            "type": "sql",
            "sql": guarded.sql,
            "tables": guarded.tables,
            "warnings": guarded.warnings,
        }
    )
    return {"sql": guarded.sql, "error": None, "warnings": guarded.warnings}


async def correct_sql(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    attempts = int(state.get("correction_attempts") or 0)
    dialect = (state.get("db_info") or {}).get("dialect", "sqlite")
    fallback = state.get("raw_sql") or state.get("sql") or ""
    corrected = await generators.correct_sql(
        llm=context.llm,
        first_prompt=state.get("sql_prompt") or "",
        failed_sql=state.get("sql") or "",
        error=state.get("error") or "",
        fallback_sql=fallback,
        dialect=dialect,
    )

    # 修正结果同样要过一遍安全网关，防止模型在「修正」时引入了不该有的表或写操作
    guarded = guard_sql(
        corrected.sql,
        allowed_tables=context.snapshot.table_names,
        dialect=dialect,
        row_limit=context.row_limit,
    )
    emit(
        {
            "type": "correction",
            "attempt": attempts + 1,
            "provider": corrected.provider,
            "reason": state.get("error"),
            "sql": guarded.sql if guarded.ok else corrected.sql,
        }
    )
    return {
        "sql": guarded.sql if guarded.ok else corrected.sql,
        "error": None if guarded.ok else guarded.error,
        "correction_attempts": attempts + 1,
        "token_usage": (state.get("token_usage") or 0) + corrected.tokens,
    }


async def run_sql(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    """执行 SQL。SQL 已经过安全校验，这里的失败基本都是数据/类型层面的问题，
    因此不抛出中断整个流水线，而是转成 error 事件，让前端能拿到明确原因。"""
    started = time.perf_counter()
    try:
        result = await context.dw_repository.run(state.get("sql", ""))
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        logger.error("SQL 执行失败：%s", message)
        emit({"type": "error", "stage": "run_sql", "message": message})
        return {
            "result": None,
            "error": message,
            "stats": {"row_count": 0, "duration_ms": int((time.perf_counter() - started) * 1000)},
        }

    duration_ms = int((time.perf_counter() - started) * 1000)

    # SSE 只推前 200 行，避免超长响应；完整结果仍在 state 里供日志与摘要使用
    emit(
        {
            "type": "result",
            "columns": result.columns,
            "rows": result.rows[:200],
            "row_count": result.row_count,
            "duration_ms": duration_ms,
        }
    )
    return {
        "result": result,
        "stats": {
            "row_count": result.row_count,
            "duration_ms": duration_ms,
            "truncated": result.row_count > 200,
        },
    }
