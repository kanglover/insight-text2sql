"""元数据仓储：把元数据库读成检索友好的快照对象。

元数据规模很小（几十张表、上百字段），因此整体加载 + 内存打分比
外部检索引擎更合适：少一个组件、少一处故障点，单测也无需 mock 网络。
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities import (
    ColumnInfo,
    MetaSnapshot,
    MetricInfo,
    QuestionSqlInfo,
    TableInfo,
    ValueInfo,
)
from app.models.meta import (
    MetaColumn,
    MetaMetric,
    MetaQuestionSql,
    MetaTable,
    MetaValue,
)


def _loads(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    return tuple(str(x) for x in data) if isinstance(data, list) else ()


class MetaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(self) -> MetaSnapshot:
        table_rows = (await self.session.execute(select(MetaTable))).scalars().all()
        column_rows = (await self.session.execute(select(MetaColumn))).scalars().all()
        metric_rows = (await self.session.execute(select(MetaMetric))).scalars().all()
        value_rows = (await self.session.execute(select(MetaValue))).scalars().all()
        example_rows = (
            (await self.session.execute(select(MetaQuestionSql))).scalars().all()
        )

        columns_by_table: dict[str, list[ColumnInfo]] = {}
        for row in column_rows:
            columns_by_table.setdefault(row.table_name, []).append(
                ColumnInfo(
                    table_name=row.table_name,
                    column_name=row.column_name,
                    data_type=row.data_type,
                    comment=row.column_comment,
                    role=row.semantic_role,
                    synonyms=_loads(row.synonyms),
                    is_primary=row.is_primary,
                )
            )

        tables = tuple(
            TableInfo(
                table_name=row.table_name,
                comment=row.table_comment,
                role=row.table_role,
                business_domain=row.business_domain,
                priority=row.priority,
                columns=tuple(columns_by_table.get(row.table_name, [])),
            )
            for row in sorted(table_rows, key=lambda r: -r.priority or 0)
        )

        metrics = tuple(
            MetricInfo(
                metric_name=row.metric_name,
                aliases=_loads(row.aliases),
                description=row.description,
                formula=row.formula,
                unit=row.unit,
                metric_type=row.metric_type,
                relevant_columns=_loads(row.relevant_columns),
            )
            for row in metric_rows
        )

        values = tuple(
            ValueInfo(
                table_name=row.table_name,
                column_name=row.column_name,
                value=row.value,
                value_desc=row.value_desc,
                synonyms=_loads(row.synonyms),
            )
            for row in value_rows
        )

        examples = tuple(
            QuestionSqlInfo(
                question=row.question,
                sql=row.sql,
                tables_used=_loads(row.tables_used),
                tags=_loads(row.tags),
                intent=row.intent,
            )
            for row in example_rows
        )

        return MetaSnapshot(tables=tables, metrics=metrics, values=values, examples=examples)
