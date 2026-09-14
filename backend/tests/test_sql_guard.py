"""SQL 安全网关测试。

这是整个项目最重要的一组单测：模型生成的东西再离谱，
也不能让数据库执行写操作或越权访问。
"""

import pytest

from app.text2sql.sql_guard import collect_tables, guard_sql

ALLOWED = [
    "dw_dim_org",
    "dw_dim_industry",
    "dw_dim_product_line",
    "dw_dim_product",
    "dw_dim_date",
    "dw_fact_revenue",
    "dw_fact_target",
    "dw_fact_project_risk",
]


def test_accepts_plain_select_and_appends_limit():
    result = guard_sql(
        "SELECT org_name, revenue FROM dw_fact_revenue",
        allowed_tables=ALLOWED,
    )
    assert result.ok
    assert result.warnings  # 自动补了 LIMIT
    assert "LIMIT" in result.sql.upper()
    assert result.tables == ["dw_fact_revenue"]


def test_keeps_existing_limit():
    result = guard_sql(
        "SELECT org_name FROM dw_fact_revenue LIMIT 5", allowed_tables=ALLOWED
    )
    assert result.ok
    assert "LIMIT 5" in result.sql.upper()
    assert result.warnings == []


def test_accepts_cte_and_union():
    sql = (
        "WITH t AS (SELECT org_id, revenue FROM dw_fact_revenue WHERE year = 2026) "
        "SELECT org_id, SUM(revenue) FROM t GROUP BY org_id"
    )
    result = guard_sql(sql, allowed_tables=ALLOWED)
    assert result.ok
    # CTE 名不应被当成物理表
    assert result.tables == ["dw_fact_revenue"]

    union = guard_sql(
        "SELECT org_id FROM dw_fact_revenue UNION SELECT org_id FROM dw_fact_target",
        allowed_tables=ALLOWED,
    )
    assert union.ok
    assert set(union.tables) == {"dw_fact_revenue", "dw_fact_target"}


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE dw_fact_revenue",
        "DELETE FROM dw_fact_revenue",
        "UPDATE dw_fact_revenue SET revenue = 0",
        "INSERT INTO dw_dim_org (org_id) VALUES (1)",
        "CREATE TABLE t (a INT)",
        "ALTER TABLE dw_fact_revenue ADD COLUMN x INT",
        "PRAGMA table_info(dw_fact_revenue)",
        "ATTACH DATABASE 'x.db' AS x",
    ],
)
def test_rejects_non_select_statements(sql):
    result = guard_sql(sql, allowed_tables=ALLOWED)
    assert not result.ok
    assert result.error


def test_rejects_multiple_statements():
    result = guard_sql(
        "SELECT org_name FROM dw_dim_org; DROP TABLE dw_dim_org", allowed_tables=ALLOWED
    )
    assert not result.ok
    assert "单条" in result.error


def test_rejects_unknown_table():
    result = guard_sql("SELECT password FROM users", allowed_tables=ALLOWED)
    assert not result.ok
    assert "users" in result.error


def test_rejects_system_table():
    result = guard_sql("SELECT name FROM sqlite_master", allowed_tables=ALLOWED)
    assert not result.ok


def test_rejects_select_star_but_allows_count_star():
    star = guard_sql("SELECT * FROM dw_dim_org", allowed_tables=ALLOWED)
    assert not star.ok
    assert "SELECT *" in star.error

    ok = guard_sql("SELECT COUNT(*) FROM dw_dim_org", allowed_tables=ALLOWED)
    assert ok.ok


def test_rejects_empty_sql():
    assert not guard_sql("   ", allowed_tables=ALLOWED).ok


def test_strips_markdown_code_fence():
    result = guard_sql(
        "```sql\nSELECT org_name FROM dw_dim_org\n```", allowed_tables=ALLOWED
    )
    assert result.ok
    assert "```" not in result.sql


def test_normalizes_chinese_alias_quotes_for_dialect():
    result = guard_sql(
        'SELECT org_name AS "经营单元" FROM dw_dim_org',
        allowed_tables=ALLOWED,
        dialect="sqlite",
    )
    assert result.ok
    assert "经营单元" in result.sql


def test_collect_tables_ignores_cte():
    sql = (
        "WITH base AS (SELECT org_id FROM dw_fact_revenue) "
        "SELECT o.org_name FROM base b JOIN dw_dim_org o ON o.org_id = b.org_id"
    )
    assert collect_tables(sql) == ["dw_fact_revenue", "dw_dim_org"]
