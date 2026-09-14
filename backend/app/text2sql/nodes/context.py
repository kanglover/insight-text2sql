"""⑤⑥⑦ 上下文收敛：合并召回 → 过滤候选表 → 组装 Prompt 上下文。"""

from datetime import date
from typing import Any

from app.core.config import settings
from app.entities import MetricInfo, TableInfo, ValueInfo
from app.text2sql.generators.rule_generator import detect_intent, extract_slots
from app.text2sql.pipeline import Emit
from app.text2sql.retrieval import build_table_context, merge_context
from app.text2sql.state import PipelineContext, PipelineState
from app.utils.text import tokenize

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def _metric_payload(metrics: list[MetricInfo]) -> list[dict[str, Any]]:
    return [
        {
            "name": m.metric_name,
            "aliases": list(m.aliases),
            "description": m.description,
            "formula": m.formula,
            "unit": m.unit,
            "metric_type": m.metric_type,
            "relevant_columns": list(m.relevant_columns),
        }
        for m in metrics
    ]


def _value_payload(values: list[ValueInfo]) -> list[dict[str, Any]]:
    return [
        {
            "table": v.table_name,
            "column": v.column_name,
            "value": v.value,
            "desc": v.value_desc,
        }
        for v in values
    ]


async def merge_retrieved_info(
    state: PipelineState, context: PipelineContext, emit: Emit
) -> dict:
    retrieval = state.get("retrieval")
    if retrieval is None:
        return {"candidate_table_names": [], "metric_infos": [], "value_infos": []}

    candidate_tables = merge_context(retrieval, context.snapshot, max_tables=8)
    metric_infos = _metric_payload([item.metric for item in retrieval.metrics])
    value_infos = _value_payload([item.value for item in retrieval.values])

    if not metric_infos:
        # 指标一路没召回时，用出现次数最多的通用指标兜底，避免 Prompt 完全没有口径信息
        metric_infos = _metric_payload([m for m in context.snapshot.metrics if m.metric_name == "收入额"])

    emit(
        {
            "type": "merge",
            "tables": [t.table_name for t in candidate_tables],
            "metrics": [m["name"] for m in metric_infos],
            "values": [f"{v['column']}={v['value']}" for v in value_infos],
        }
    )
    return {
        "candidate_table_names": [t.table_name for t in candidate_tables],
        "table_infos_candidates": candidate_tables,
        "metric_infos": metric_infos,
        "value_infos": value_infos,
    }


async def filter_table(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    candidates: list[TableInfo] = state.get("table_infos_candidates") or []
    kept = candidates[: settings.recall_max_tables]

    # 只在候选里挑还不够：事实表被选中、维表被阈值滤掉时，模型会写出无法执行的 join。
    # 这里用 ForeignKey 反推出的表关系补齐一跳维表，保证 join 一定连得通。
    from app.text2sql.schema_graph import expand_with_dimensions, pick_fact_table

    retrieval = state.get("retrieval")
    relevant: set[str] = set()
    if retrieval is not None:
        relevant |= {item.column.table_name for item in retrieval.columns}
        relevant |= {item.value.table_name for item in retrieval.values}

    names = expand_with_dimensions(
        [t.table_name for t in kept], relevant, settings.recall_max_tables + 2
    )
    if not any(context.snapshot.table(n) and context.snapshot.table(n).role == "fact" for n in names):
        extra_fact = pick_fact_table(names)
        if extra_fact:
            names = [extra_fact, *names]

    kept = [t for t in (context.snapshot.table(n) for n in names) if t is not None]
    selected = [t.table_name for t in kept]
    emit({"type": "tables", "selected": selected})
    return {"selected_tables": selected, "table_infos_selected": kept}


def _pick_examples(state: PipelineState, context: PipelineContext, limit: int = 3) -> list[dict]:
    """选 few-shot 样例：优先同意图，其次问题词重合度高的。"""
    query = state.get("query", "")
    slots = extract_slots(query, context.snapshot)
    intent = detect_intent(query, slots)
    query_tokens = set(tokenize(query))

    def overlap(example) -> int:
        return len(query_tokens & set(tokenize(example.question)))

    examples = list(context.snapshot.examples)
    same_intent = [e for e in examples if e.intent == intent]
    same_intent.sort(key=lambda e: -overlap(e))
    picked = same_intent[:limit]

    if len(picked) < limit:
        rest = [e for e in examples if e not in picked]
        rest.sort(key=lambda e: -overlap(e))
        picked.extend(rest[: limit - len(picked)])

    return [
        {"question": e.question, "sql": e.sql, "intent": e.intent} for e in picked
    ]


async def add_extra_context(
    state: PipelineState, context: PipelineContext, emit: Emit
) -> dict:
    today = date.today()
    date_info = {
        "date": today.strftime("%Y-%m-%d"),
        "weekday": WEEKDAY_CN[today.weekday()],
        "quarter": f"Q{(today.month - 1) // 3 + 1}",
    }
    db_info = await context.dw_repository.get_db_info()
    examples = _pick_examples(state, context)

    emit(
        {
            "type": "context",
            "date": date_info["date"],
            "dialect": db_info.get("dialect", ""),
            "version": db_info.get("version", ""),
            "examples": [e["question"] for e in examples],
        }
    )
    return {"date_info": date_info, "db_info": db_info, "examples": examples}


async def build_sql_context(
    state: PipelineState, context: PipelineContext, emit: Emit
) -> dict:
    """把候选表转成最终给模型看的表结构上下文，并附上可用的 join 路径。"""
    from app.text2sql.schema_graph import join_paths

    tables: list[TableInfo] = state.get("table_infos_selected") or []
    paths = join_paths([t.table_name for t in tables])
    return {"candidate_tables": build_table_context(tables), "join_paths": paths}
