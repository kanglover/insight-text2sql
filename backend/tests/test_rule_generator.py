"""规则引擎测试：意图识别、槽位抽取、SQL 可执行性。

这组用例同时充当「数据口径」的回归测试：
如果哪天改了种子数据或指标定义导致这些断言挂了，说明口径被改动了。
"""

import pytest
import sqlalchemy as sa

from app.text2sql.generators.rule_generator import (
    detect_intent,
    extract_slots,
    generate_with_rules,
)
from app.text2sql.sql_guard import guard_sql


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("2026年各经营单元的收入排名", "org_revenue_rank"),
        ("2026年各经营单元的收入和完成率", "org_target_rate"),
        ("2026年商业目标TOP5的经营单元", "org_target_compare"),
        ("2026年各行业的收入是多少", "industry_revenue"),
        ("政企行业收入在3000万到5000万之间的经营单元", "industry_filter"),
        ("2026年各产品线的收入占比", "product_line_revenue"),
        ("2026年销售最好的3个产品型号", "product_top"),
        ("2026年每月的合同金额趋势", "monthly_trend"),
        ("2025年和2026年各产品线的同比变化", "yoy_trend"),
        ("目前有多少个高风险项目", "risk_count"),
        ("高风险项目有哪些", "risk_list"),
        ("北京代表处今年的达成情况", "org_detail"),
        ("2026年各大区的收入情况", "region_revenue"),
        ("2026年各经营单元的回款率排名", "collection_rate"),
        ("2026年各行业的订单数", "order_count"),
        ("2025年各季度的收入是多少", "quarterly_revenue"),
        ("各组织层级的收入对比", "org_level_revenue"),
        ("2026年各产品线的商业目标和商解目标", "product_line_target"),
        ("2026年1-9月各经营单元收入同比", "org_yoy"),
        ("项目风险按类型分布情况", "risk_by_type"),
    ],
)
def test_detect_intent(question, intent, snapshot):
    slots = extract_slots(question, snapshot)
    assert detect_intent(question, slots) == intent


def test_extract_slots_year_limit_and_entities(snapshot):
    slots = extract_slots("2025年北京代表处收入TOP3", snapshot)
    assert slots.year == 2025
    assert slots.org == "北京代表处"
    assert slots.requested_count == 3


def test_extract_slots_amount_range_and_industry_alias(snapshot):
    slots = extract_slots("政企行业收入在3000万到5000万之间", snapshot)
    assert slots.industry == "数字政府"  # 口语「政企」映射到标准行业名
    assert (slots.amount_min, slots.amount_max) == (3000.0, 5000.0)


@pytest.mark.parametrize(
    "question",
    [
        "2026年各经营单元的收入排名",
        "2026年各产品线的收入占比",
        "高风险项目有哪些",
        "2026年每月合同金额趋势",
        "2026年各行业的订单数",
    ],
)
def test_generated_sql_passes_guard(question, snapshot):
    rule = generate_with_rules(question, snapshot)
    result = guard_sql(rule.sql, allowed_tables=snapshot.table_names, dialect="sqlite")
    assert result.ok, result.error


@pytest.mark.parametrize(
    ("question", "min_rows"),
    [
        ("2026年各经营单元的收入和完成率", 20),
        ("2026年各行业的收入排名", 14),
        ("高风险项目有哪些", 7),
        ("目前有多少个高风险项目", 1),
        ("2026年各大区的收入情况", 6),
    ],
)
@pytest.mark.asyncio
async def test_rule_queries_are_executable_and_return_rows(question, min_rows, database):
    """规则引擎产出的 SQL 必须真的能跑、并且真的查得到数据。"""
    from app.repositories.meta_repository import MetaRepository

    async with database.session() as session:
        snapshot = await MetaRepository(session).snapshot()
        rule = generate_with_rules(question, snapshot)
        guarded = guard_sql(rule.sql, allowed_tables=snapshot.table_names)
        assert guarded.ok, guarded.error
        rows = (await session.execute(sa.text(guarded.sql))).fetchall()
        assert len(rows) >= min_rows, f"{question} 只查到 {len(rows)} 行"


@pytest.mark.asyncio
async def test_completion_rate_matches_seed_caliber(database):
    """2026 年北京代表处完成率应贴近 demo 里展示的 ~78%。"""
    from app.repositories.meta_repository import MetaRepository

    async with database.session() as session:
        snapshot = await MetaRepository(session).snapshot()
        rule = generate_with_rules("2026年各经营单元的收入和完成率", snapshot)
        guarded = guard_sql(rule.sql, allowed_tables=snapshot.table_names)
        rows = (await session.execute(sa.text(guarded.sql))).mappings().all()
        row = next(r for r in rows if r["经营单元"] == "北京代表处")
        assert 75 <= float(row["完成率"]) <= 82
