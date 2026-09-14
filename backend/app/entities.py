"""领域实体：元数据的只读视图对象。

放在这里而不是直接复用 ORM 模型，是为了让检索/生成环节不依赖数据库会话，
纯粹围绕不可变数据做计算，单测时可以直接构造。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColumnInfo:
    table_name: str
    column_name: str
    data_type: str
    comment: str
    role: str  # dimension / measure / date / id
    synonyms: tuple[str, ...] = ()
    is_primary: int = 0

    @property
    def qualified_name(self) -> str:
        return f"{self.table_name}.{self.column_name}"


@dataclass(frozen=True)
class TableInfo:
    table_name: str
    comment: str
    role: str
    business_domain: str = ""
    priority: int = 0
    columns: tuple[ColumnInfo, ...] = ()

    @property
    def dimensions(self) -> tuple[ColumnInfo, ...]:
        return tuple(c for c in self.columns if c.role in {"dimension", "date"})

    @property
    def measures(self) -> tuple[ColumnInfo, ...]:
        return tuple(c for c in self.columns if c.role == "measure")


@dataclass(frozen=True)
class MetricInfo:
    metric_name: str
    aliases: tuple[str, ...]
    description: str
    formula: str
    unit: str
    metric_type: str
    relevant_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValueInfo:
    table_name: str
    column_name: str
    value: str
    value_desc: str = ""
    synonyms: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.table_name}.{self.column_name}"


@dataclass(frozen=True)
class QuestionSqlInfo:
    question: str
    sql: str
    tables_used: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    intent: str = ""


@dataclass(frozen=True)
class MetaSnapshot:
    """一次问数所需的元数据全量视图。"""

    tables: tuple[TableInfo, ...] = ()
    metrics: tuple[MetricInfo, ...] = ()
    values: tuple[ValueInfo, ...] = ()
    examples: tuple[QuestionSqlInfo, ...] = ()

    def table(self, name: str) -> TableInfo | None:
        for t in self.tables:
            if t.table_name == name:
                return t
        return None

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(t.table_name for t in self.tables)


@dataclass
class QueryResult:
    """SQL 执行结果。"""

    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def as_dicts(self, limit: int | None = None) -> list[dict[str, Any]]:
        data = self.rows if limit is None else self.rows[:limit]
        return [dict(zip(self.columns, row, strict=False)) for row in data]
