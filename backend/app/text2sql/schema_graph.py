"""表关系图：从 SQLAlchemy 的 ForeignKey 定义反推 join 关系。

为什么不用注释里的「关联 dw_dim_org」这类文字描述？
因为文字会写错、会过时，而 ForeignKey 是数据库层面的事实。
把它变成一张可查询的 join 表后：
- `filter_table` 可以自动补全「事实表需要的维表」，保证生成的 SQL 能 join 通；
- Prompt 里可以直接给出「可用连接路径」，明显降低模型写错 join 条件的概率。
"""

from functools import lru_cache

# 触发模型注册
from app import models  # noqa: F401
from app.db.base import Base


@lru_cache
def join_map() -> dict[str, list[tuple[str, str, str]]]:
    """返回 {表名: [(本表外键列, 目标表, 目标列), ...]}。"""
    result: dict[str, list[tuple[str, str, str]]] = {}
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            result.setdefault(table.name, []).append(
                (fk.parent.name, fk.column.table.name, fk.column.name)
            )
    return result


@lru_cache
def reverse_join_map() -> dict[str, list[tuple[str, str, str]]]:
    """返回 {表名: [(引用本表的表, 该表的外键列, 本表被引用的列), ...]}。"""
    result: dict[str, list[tuple[str, str, str]]] = {}
    for source, relations in join_map().items():
        for source_column, target_table, target_column in relations:
            result.setdefault(target_table, []).append((source, source_column, target_column))
    return result


def expand_with_dimensions(
    selected: list[str], relevant: set[str] | None = None, max_tables: int = 8
) -> list[str]:
    """把选中的表向外扩一跳：事实表带上它需要的维表。

    为什么只扩一跳、而且只扩「与问题相关」的维表？
    - 星型模型里事实表到维表就是一跳，多跳会把不相干的表拉进来；
    - 把全部维表都塞进 Prompt 会让上下文退化成「整库 schema」，
      既浪费 Token 也削弱检索本身的价值。
    `relevant` 由召回结果给出（被召回字段/取值所在的表），
    因此「问到行业就带行业维表，没问到就不带」。
    """
    result = list(selected)
    allow = relevant if relevant is not None else None
    for name in selected:
        for _, target_table, _ in join_map().get(name, []):
            if target_table in result:
                continue
            if allow is not None and target_table not in allow:
                continue
            result.append(target_table)
    return result[:max_tables]


def pick_fact_table(selected: list[str]) -> str | None:
    """如果选中的全是维表，挑一张能连上它们的、优先级最高的事实表。"""
    candidates: list[str] = []
    for name in selected:
        for source, _, _ in reverse_join_map().get(name, []):
            if source not in candidates:
                candidates.append(source)
    if not candidates:
        return None
    # 依据元数据优先级排序（事实表优先级普遍高于维表）
    from app.data.metadata import TABLES_BY_NAME

    candidates.sort(key=lambda t: -TABLES_BY_NAME[t].priority if t in TABLES_BY_NAME else 0)
    for name in candidates:
        if name not in selected:
            return name
    return None


def join_paths(selected: list[str]) -> list[str]:
    """生成「A.col = B.col」形式的可读连接路径，供 Prompt 与前端展示。"""
    paths: list[str] = []
    allow = set(selected)
    for source, relations in join_map().items():
        if source not in allow:
            continue
        for source_column, target_table, target_column in relations:
            if target_table in allow:
                paths.append(f"{source}.{source_column} = {target_table}.{target_column}")
    return sorted(paths)
