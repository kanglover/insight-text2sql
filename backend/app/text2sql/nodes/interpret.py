"""⑫ 结果解读：图表规格 + 数据统计 + 自然语言结论 + 延伸问题。

图表规格由后端推导，前端只负责渲染。好处是：
- 同一份结果在「智能问数」和后续的「报表」里能复用同一套渲染规则；
- 推导逻辑是纯函数，可以直接单测（见 `tests/test_chart.py`）。
"""

from typing import Any

from app.core.log import get_logger
from app.entities import QueryResult
from app.text2sql.generators.llm_generator import llm_followups, llm_summarize
from app.text2sql.llm import LLMUnavailable
from app.text2sql.pipeline import Emit
from app.text2sql.state import PipelineContext, PipelineState
from app.utils.text import tokenize

logger = get_logger(__name__)

# 这些列名看起来是「轴」而不是「度量」
_AXIS_HINTS = ("年份", "年", "季度", "月份", "月", "日期", "天", "时间")
_RATIO_HINTS = ("占比", "比例", "完成率", "回款率", "率", "同比", "增幅")
_MAX_POINTS = 30
_MAX_PIE_SLICES = 10


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_columns(columns: list[str], rows: list[list[Any]]) -> list[int]:
    indexes: list[int] = []
    for i, _ in enumerate(columns):
        values = [row[i] for row in rows if row[i] is not None]
        if values and all(_is_number(v) for v in values):
            indexes.append(i)
    return indexes


def _is_axis_name(name: str) -> bool:
    """列名是否像「时间轴」：年份/季度/月份/日期这类列即便是数字，也应作为横轴。"""
    return any(hint == name or hint in name for hint in _AXIS_HINTS)


def _pick_axis(columns: list[str], rows: list[list[Any]], numeric_idx: list[int]) -> int | None:
    """挑选横轴列。

    优先级：
    1. 时间类列（年份/季度/月份/日期）——若出现多个，取取值最丰富的那个，
       例如「年份 + 季度」同时存在时选季度，避免横轴全是同一个年份；
    2. 第一个非数值列（类别轴，比如「经营单元」「行业」）；
    3. 都没有则返回 None，由调用方退化成指标卡或使用序号轴。
    """
    time_axis = [i for i, name in enumerate(columns) if _is_axis_name(name)]
    if time_axis:
        return max(time_axis, key=lambda i: len({row[i] for row in rows}))
    numeric_set = set(numeric_idx)
    for i in range(len(columns)):
        if i not in numeric_set:
            return i
    return None


def build_chart(columns: list[str], rows: list[list[Any]]) -> dict[str, Any] | None:
    """从查询结果推导图表规格。返回值直接给前端渲染。"""
    if not columns or not rows:
        return None

    numeric_idx = _numeric_columns(columns, rows)
    axis_idx = _pick_axis(columns, rows, numeric_idx)

    # 度量列 = 数值列，排除横轴列与 id 类列（id 当指标没有业务意义）
    series_idx = [
        i for i in numeric_idx if i != axis_idx and not _looks_like_axis(columns[i])
    ]
    if not series_idx:  # id 过滤太狠时兜底，至少保证有图可画
        series_idx = [i for i in numeric_idx if i != axis_idx]
    if not series_idx:
        return None

    series_names = [columns[i] for i in series_idx]

    # 单行且无类别轴（如「高风险项目数 + 风险金额」）→ 指标卡
    if len(rows) == 1 and axis_idx is None:
        return {
            "type": "metric",
            "metrics": [{"label": columns[i], "value": rows[0][i]} for i in series_idx],
        }

    axis_name = columns[axis_idx] if axis_idx is not None else None
    axis_values = (
        [row[axis_idx] for row in rows]
        if axis_idx is not None
        else list(range(1, len(rows) + 1))
    )

    if len(rows) == 1:
        return {
            "type": "metric",
            "metrics": [{"label": columns[i], "value": rows[0][i]} for i in series_idx],
        }

    # 单个占比/比例度量且分片不多 → 饼图
    if (
        len(series_names) == 1
        and any(hint in series_names[0] for hint in ("占比", "比例"))
        and len(rows) <= _MAX_PIE_SLICES
    ):
        values = [row[series_idx[0]] for row in rows]
        return {
            "type": "pie",
            "name": series_names[0],
            "data": [
                {"name": axis_values[i], "value": values[i]} for i in range(len(rows))
            ],
        }

    limited = min(len(rows), _MAX_POINTS)
    is_time_axis = axis_name is not None and _is_axis_name(axis_name)
    chart_type = "line" if is_time_axis else "bar"
    data = [
        {"name": axis_values[i], **{columns[j]: rows[i][j] for j in series_idx}}
        for i in range(limited)
    ]
    chart: dict[str, Any] = {"type": chart_type, "series": series_names, "data": data}
    if axis_name is not None:
        chart["x"] = axis_name
    return chart


def _looks_like_axis(name: str) -> bool:
    return any(hint == name or hint in name for hint in ("id", "ID", "编码"))


def build_stats(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    """对每个数值列给出 合计/平均/最大/最小，对应 demo 的「数据统计」。"""
    stats: dict[str, Any] = {"row_count": len(rows), "measures": []}
    if not rows:
        return stats
    for i, name in enumerate(columns):
        values = [row[i] for row in rows if _is_number(row[i])]
        if not values or _looks_like_axis(name):
            continue
        stats["measures"].append(
            {
                "name": name,
                "sum": round(sum(values), 2),
                "avg": round(sum(values) / len(values), 2),
                "max": max(values),
                "min": min(values),
                "count": len(values),
            }
        )
    return stats


def format_value(value: Any) -> str:
    if _is_number(value):
        if isinstance(value, float) and not value.is_integer():
            return f"{value:,.1f}"
        return f"{int(value):,}"
    return str(value)


def template_answer(query: str, columns: list[str], rows: list[list[Any]]) -> str:
    """不依赖大模型的结论模板：保证离线也有可读输出。"""
    if not rows:
        return "未查询到符合条件的数据。可以尝试放宽筛选条件，或确认问题中提到的经营单元、行业名称是否与系统口径一致。"

    lines = [f"共查询到 {len(rows)} 条记录。"]
    # 找出最可能是度量的列，用来排序并给出 Top 榜
    numeric_idx = _numeric_columns(columns, rows)
    ranked = list(range(len(rows)))
    if numeric_idx:
        key = numeric_idx[0]
        ranked.sort(key=lambda i: (rows[i][key] if _is_number(rows[i][key]) else float("-inf")), reverse=True)

    header = "，".join(
        f"{columns[c]}={format_value(rows[ranked[0]][c])}" for c in range(min(len(columns), 3))
    )
    lines.append(f"1. 排名第一：{header}")
    for order, i in enumerate(ranked[1:4], start=2):
        row = rows[i]
        detail = "，".join(
            f"{columns[c]} {format_value(row[c])}" for c in range(min(len(columns), 4))
        )
        lines.append(f"{order}. {detail}")
    if len(rows) > 4:
        lines.append(f"（其余 {len(rows) - 4} 条已在上方明细表中展示）")
    return "\n".join(lines)


def _related_questions(state: PipelineState, context: PipelineContext, limit: int = 3) -> list[str]:
    """离线时的延伸问题：从样例库里挑词重合度最高的其它问题。"""
    query = state.get("query", "")
    tokens = set(tokenize(query))
    scored: list[tuple[int, str]] = []
    for example in context.snapshot.examples:
        if example.question == query:
            continue
        score = len(tokens & set(tokenize(example.question)))
        scored.append((score, example.question))
    scored.sort(key=lambda item: -item[0])
    picked: list[str] = []
    for _, question in scored:
        if question not in picked:
            picked.append(question)
        if len(picked) >= limit:
            break
    return picked


async def interpret_result(
    state: PipelineState, context: PipelineContext, emit: Emit
) -> dict:
    result: QueryResult | None = state.get("result")
    columns = result.columns if result else []
    rows = result.rows if result else []
    tokens = state.get("token_usage") or 0

    chart = build_chart(columns, rows)
    stats = build_stats(columns, rows)

    answer = ""
    if result is None and state.get("error"):
        answer = f"查询执行失败：{state['error']}"
    elif context.llm.available and rows:
        try:
            answer, used = await llm_summarize(
                context.llm,
                query=state.get("query", ""),
                sql=state.get("sql", ""),
                columns=columns,
                rows=rows,
            )
            tokens += used
        except LLMUnavailable as exc:
            logger.warning("结论生成失败，使用模板摘要：%s", exc)
    if not answer:
        answer = template_answer(state.get("query", ""), columns, rows)

    followups = await llm_followups(
        context.llm, query=state.get("query", ""), columns=columns
    ) if context.llm.available else []
    if not followups:
        followups = _related_questions(state, context)

    emit({"type": "chart", "chart": chart})
    emit({"type": "stats", "stats": stats})
    emit({"type": "answer", "answer": answer, "followups": followups})
    return {
        "chart": chart,
        "stats": {**stats, "tokens": tokens},
        "answer": answer,
        "followups": followups,
        "token_usage": tokens,
    }
