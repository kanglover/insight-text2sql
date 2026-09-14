"""问数流水线的图定义。

```
START
  └─ ① 解析问题与关键词        extract_keywords
      ├─ ② 召回相关字段        recall_column
      ├─ ③ 召回业务指标        recall_metric
      └─ ④ 召回字段取值        recall_value
          └─ ⑤ 合并检索结果     merge_retrieved_info
              └─ ⑥ 收敛数据表    filter_table
                  └─ ⑦ 补充上下文 add_extra_context
                      └─ ⑧ 组装 SQL 上下文 build_sql_context
                          └─ ⑨ 生成 SQL   generate_sql
                              └─ ⑩ 校验 SQL  validate_sql
                                   ├─ 通过 → ⑫ 执行取数 run_sql
                                   └─ 失败 → ⑪ 自动修正 correct_sql → run_sql
                                                          └─ ⑬ 生成结论与图表 interpret_result
                                                              └─ END
```

三路召回在本实现里顺序执行，但它们都是纯内存打分（毫秒级、无 IO），
顺序执行换来了「单测可追踪、日志线性可读」的收益。
节点数或分支继续增长时，只需把 `pipeline.py` 换成图框架，节点函数不必改。
"""

from app.text2sql.nodes import (
    add_extra_context,
    build_sql_context,
    correct_sql,
    extract_keywords,
    filter_table,
    generate_sql,
    interpret_result,
    merge_retrieved_info,
    recall_column,
    recall_metric,
    recall_value,
    run_sql,
    validate_sql,
)
from app.text2sql.pipeline import ConditionalEdge, Edge, Node, Pipeline


def build_pipeline() -> Pipeline:
    pipeline = Pipeline(name="insight_text2sql", entry="extract_keywords")

    nodes = [
        Node("extract_keywords", "① 解析问题与关键词", extract_keywords),
        Node("recall_column", "② 召回相关字段", recall_column),
        Node("recall_metric", "③ 召回业务指标", recall_metric),
        Node("recall_value", "④ 召回字段取值", recall_value),
        Node("merge_retrieved_info", "⑤ 合并检索结果", merge_retrieved_info),
        Node("filter_table", "⑥ 收敛候选数据表", filter_table),
        Node("add_extra_context", "⑦ 补充日期与数据库上下文", add_extra_context),
        Node("build_sql_context", "⑧ 组装 SQL 生成上下文", build_sql_context),
        Node("generate_sql", "⑨ 生成 SQL", generate_sql),
        Node("validate_sql", "⑩ 校验 SQL 安全性", validate_sql),
        Node("correct_sql", "⑪ 自动修正 SQL", correct_sql),
        Node("run_sql", "⑫ 执行取数", run_sql),
        Node("interpret_result", "⑬ 生成结论与图表", interpret_result),
    ]
    edges = {
        "extract_keywords": "recall_column",
        "recall_column": "recall_metric",
        "recall_metric": "recall_value",
        "recall_value": "merge_retrieved_info",
        "merge_retrieved_info": "filter_table",
        "filter_table": "add_extra_context",
        "add_extra_context": "build_sql_context",
        "build_sql_context": "generate_sql",
        "generate_sql": "validate_sql",
        "correct_sql": "run_sql",
        "run_sql": "interpret_result",
        "interpret_result": "END",
    }
    for node in nodes:
        pipeline.add(node, edges.get(node.name))

    # 校验失败且还没修正过 → 走修正；否则直接执行（执行节点的异常会转成 error 事件）
    pipeline.branch(
        "validate_sql",
        router=_validate_router,
        mapping={"run_sql": "run_sql", "correct_sql": "correct_sql"},
    )
    return pipeline


def _validate_router(state: dict) -> str:
    if state.get("error") is None:
        return "run_sql"
    if int(state.get("correction_attempts") or 0) == 0:
        return "correct_sql"
    return "run_sql"


pipeline = build_pipeline()

# 便于文档与调试：pipeline.mermaid()
__all__ = ["pipeline", "build_pipeline", "Pipeline", "Node", "Edge", "ConditionalEdge"]
