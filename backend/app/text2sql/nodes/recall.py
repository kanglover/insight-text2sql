"""②③④ 三路召回：字段 / 指标 / 取值。

三路互相独立，放在同一模块里是为了让「召回」这件事只有一处实现，
后续要换成向量检索只需替换 `retrieval.py` 里的实现。
"""

from app.text2sql.pipeline import Emit
from app.text2sql.retrieval import (
    RetrievalResult,
    recall_columns,
    recall_metrics,
    recall_values,
)
from app.text2sql.state import PipelineContext, PipelineState


def _retrieval(state: PipelineState) -> RetrievalResult:
    cached = state.get("retrieval")
    if cached is None:
        cached = RetrievalResult()
    return cached


async def recall_column(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    result = _retrieval(state)
    result.terms = result.terms or []
    result.columns = recall_columns(state.get("query", ""), state.get("keywords", []), context.snapshot)
    emit(
        {
            "type": "recall",
            "stage": "column",
            "count": len(result.columns),
            "items": [
                {
                    "name": item.column.qualified_name,
                    "comment": item.column.comment,
                    "score": item.score,
                }
                for item in result.columns[:8]
            ],
        }
    )
    return {"retrieval": result}


async def recall_metric(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    result = _retrieval(state)
    result.metrics = recall_metrics(state.get("query", ""), state.get("keywords", []), context.snapshot)
    emit(
        {
            "type": "recall",
            "stage": "metric",
            "count": len(result.metrics),
            "items": [
                {"name": item.metric.metric_name, "spec": item.metric.formula, "score": item.score}
                for item in result.metrics[:6]
            ],
        }
    )
    return {"retrieval": result}


async def recall_value(state: PipelineState, context: PipelineContext, emit: Emit) -> dict:
    result = _retrieval(state)
    result.values = recall_values(state.get("query", ""), context.snapshot)
    emit(
        {
            "type": "recall",
            "stage": "value",
            "count": len(result.values),
            "items": [
                {
                    "name": f"{item.value.column_name} = {item.value.value}",
                    "score": item.score,
                }
                for item in result.values[:8]
            ],
        }
    )
    return {"retrieval": result}
