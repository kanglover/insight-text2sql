"""SQL 安全网关。

大模型生成的 SQL 在落到数据库之前必须过这一关。策略是「白名单 + 规范化」，
而不是「黑名单关键词」——黑名单永远列不全，白名单天然收敛：

1. 必须能被 sqlglot 解析，且只有一条语句（拒绝 `select 1; drop table x`）；
2. 顶层必须是查询节点（SELECT / UNION / CTE），任何 DDL、DML、PRAGMA 一律拒绝；
3. 引用的表必须全部在元数据白名单里，且禁止访问 sqlite_master 等系统表；
4. 禁止 `SELECT *`，必须显式列出字段（既便于前端映射中文表头，也避免拉回无用列）；
5. 没有 LIMIT 时自动补上，避免全表扫描把内存打满；
6. 按目标方言重新生成 SQL（中文等标识符的引号风格由 sqlglot 负责转换）。
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

# 允许出现在顶层的结果集节点
_ALLOWED_QUERY_NODES = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# 禁止访问的系统表 / 危险函数
_FORBIDDEN_TABLES = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_sequence"}
_FORBIDDEN_FUNCTIONS = {"load_extension", "readfile", "writefile", "fts3_tokenizer"}


@dataclass
class GuardResult:
    sql: str
    tables: list[str] = field(default_factory=list)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None


def _cte_names(tree: exp.Expression) -> set[str]:
    names = set()
    for cte in tree.find_all(exp.CTE):
        alias = cte.alias
        if alias:
            names.add(alias.lower())
    return names


def _order_by_appearance(names: list[str], sql: str) -> list[str]:
    """按表名在 SQL 文本中首次出现的位置排序。

    为什么要自己排：sqlglot 的 `find_all` 是语法树遍历，顺序并不等于书写顺序
    （例如带 CTE 时可能先访问外层 FROM 再访问 CTE 内部）。对使用者来说，
    「SQL 里先写到的表排前面」才是可预期的确定行为。
    """
    lowered = sql.lower()
    return sorted(names, key=lambda name: lowered.find(name))


def collect_tables(sql: str, dialect: str = "sqlite") -> list[str]:
    """收集 SQL 里引用的物理表名（已排除 CTE 别名），按书写顺序返回。"""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return []
    ctes = _cte_names(tree)
    tables: list[str] = []
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if not name or name in ctes:
            continue
        if name not in tables:
            tables.append(name)
    return _order_by_appearance(tables, sql)


def guard_sql(
    sql: str,
    *,
    allowed_tables: list[str] | tuple[str, ...],
    dialect: str = "sqlite",
    row_limit: int = 500,
) -> GuardResult:
    """校验并规范化 SQL。校验不通过时返回带 error 的结果，不抛异常。"""
    raw = (sql or "").strip()
    if not raw:
        return GuardResult(sql="", error="SQL 为空")

    # 去掉模型可能包裹的 markdown 代码块
    if raw.startswith("```"):
        raw = raw.strip("`")
        if "\n" in raw:
            first, _, rest = raw.partition("\n")
            if first.strip().lower() in {"sql", "sqlite", "mysql", "postgresql"}:
                raw = rest
        raw = raw.strip().rstrip("`").strip()

    statements = sqlglot.parse(raw, read=dialect)
    statements = [s for s in statements if s is not None]
    if not statements:
        return GuardResult(sql=raw, error="无法解析该 SQL")
    if len(statements) > 1:
        return GuardResult(sql=raw, error="只允许执行单条 SQL，检测到多条语句")

    tree = statements[0]
    if not isinstance(tree, _ALLOWED_QUERY_NODES):
        return GuardResult(
            sql=raw,
            error=f"只允许执行只读查询，检测到 {type(tree).__name__} 类型的语句",
        )

    ctes = _cte_names(tree)
    allowed = {t.lower() for t in allowed_tables}
    used: list[str] = []
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if not name or name in ctes:
            continue
        if name in _FORBIDDEN_TABLES:
            return GuardResult(sql=raw, error=f"禁止访问系统表 {name}")
        if name not in allowed:
            return GuardResult(sql=raw, error=f"表 {name} 不在允许访问的元数据白名单中")
        if name not in used:
            used.append(name)

    used = _order_by_appearance(used, raw)

    for func in tree.find_all(exp.Func):
        fname = (func.sql_name() or "").lower()
        if fname in _FORBIDDEN_FUNCTIONS:
            return GuardResult(sql=raw, error=f"禁止调用函数 {fname}")

    warnings: list[str] = []
    # 禁止 SELECT *：只检查投影列，COUNT(*) 里的星号不算
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Star):
                return GuardResult(sql=raw, error="不允许使用 SELECT *，请显式列出需要的字段")
    # 注意：select.expressions 也可能出现 "table.*"，这里同样拦截
    if any(isinstance(col, exp.Column) and isinstance(col.this, exp.Star) for col in tree.find_all(exp.Column)):
        return GuardResult(sql=raw, error="不允许使用 SELECT *，请显式列出需要的字段")

    if tree.args.get("limit") is None:
        tree = tree.limit(row_limit)
        warnings.append(f"未指定 LIMIT，已自动追加 LIMIT {row_limit}")

    try:
        normalized = tree.sql(dialect=dialect)
    except Exception as exc:  # pragma: no cover - 依赖 sqlglot 内部异常
        return GuardResult(sql=raw, error=f"SQL 方言转换失败：{exc}")

    return GuardResult(sql=normalized, tables=used, warnings=warnings)
