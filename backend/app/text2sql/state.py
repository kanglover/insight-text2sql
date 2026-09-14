"""流水线状态定义。

节点之间只通过这个字典通信；外部依赖（仓储、LLM）走 context，不进状态。
这样每个节点都可以脱离图单独测试：构造一个 dict + 一个假的 context 即可。
"""

from dataclasses import dataclass, field
from typing import Any, TypedDict

from app.entities import MetaSnapshot, QueryResult
from app.repositories.dw_repository import DwRepository
from app.repositories.meta_repository import MetaRepository
from app.text2sql.llm import LLMClient


class PipelineState(TypedDict, total=False):
    # ---- 输入 ----
    query: str

    # ---- 召回与上下文 ----
    keywords: list[str]
    retrieval: Any  # RetrievalResult，放在这里避免 state 模块反向依赖 retrieval
    candidate_table_names: list[str]
    candidate_tables: list[dict[str, Any]]
    table_infos_candidates: Any  # list[TableInfo]，合并召回后的候选表
    table_infos_selected: Any  # list[TableInfo]，最终进入 Prompt 的表
    metric_infos: list[dict[str, Any]]
    value_infos: list[dict[str, Any]]
    selected_tables: list[str]
    date_info: dict[str, str]
    db_info: dict[str, str]
    examples: list[dict[str, Any]]
    join_paths: list[str]

    # ---- 生成与执行 ----
    sql: str
    raw_sql: str
    provider: str
    error: str | None
    warnings: list[str]
    correction_attempts: int

    # ---- 产出 ----
    result: QueryResult | None
    stats: dict[str, Any]
    chart: dict[str, Any] | None
    answer: str
    followups: list[str]
    token_usage: int


@dataclass
class PipelineContext:
    """一次问数执行所需的全部外部依赖。"""

    meta_repository: MetaRepository
    dw_repository: DwRepository
    llm: LLMClient
    snapshot: MetaSnapshot
    provider: str = "auto"
    max_correction_retry: int = 1
    row_limit: int = 500
    extras: dict[str, Any] = field(default_factory=dict)
