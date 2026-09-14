"""数仓与元数据知识库的种子数据生成。

特点：
- 完全确定性（固定 random 种子），任何人任何机器生成的数据一致，单测可断言具体数值；
- 口径自洽：2026 年 1-9 月各经营单元收入 ≈ ORG_BASE_REVENUE，
  与 ORG_BIZ_TARGET 相除即得到 demo 里那种「完成率」；
- 元数据从 `metadata.py` 与 `qa_examples.py` 派生，不重复维护。
"""

import json
import random
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, insert

from app.data.dimensions import (
    DATA_CUTOFF_MONTH_2026,
    INDUSTRY_WEIGHT,
    INDUSTRIES,
    MONTH_SEASONALITY,
    ORG_BASE_REVENUE,
    ORG_BIZ_TARGET,
    ORG_GROWTH,
    ORGS,
    PRODUCT_LINE_ORDER_PRICE,
    PRODUCT_LINE_WEIGHT,
    PRODUCT_LINES,
    PRODUCTS,
    RISK_PROJECT_ORGS,
    RISK_PROJECTS,
    SOL_TARGET_RATIO,
)
from app.data.metadata import METRIC_SPECS, TABLE_SPECS
from app.data.qa_examples import QA_EXAMPLES

SEED = 20260911

MONTHS_1_9 = sum(MONTH_SEASONALITY[:DATA_CUTOFF_MONTH_2026])
MONTHS_ALL = sum(MONTH_SEASONALITY)
SEASON_1_9 = [f / MONTHS_1_9 for f in MONTH_SEASONALITY[:DATA_CUTOFF_MONTH_2026]]
SEASON_ALL = [f / MONTHS_ALL for f in MONTH_SEASONALITY]


def _jitter(rng: random.Random, low: float, high: float) -> float:
    return rng.uniform(low, high)


# ---------------------------------------------------------------- 维度


def build_dims() -> dict[str, list[dict[str, Any]]]:
    orgs = [
        {
            "org_id": i + 1,
            "org_code": f"ORG{i + 1:03d}",
            "org_name": name,
            "org_level": level,
            "region": region,
            "parent_org": "总部" if level == "系统部" else region + "大区",
        }
        for i, (name, level, region) in enumerate(ORGS)
    ]
    industries = [
        {"industry_id": i + 1, "industry_name": name, "industry_group": group}
        for i, (name, group) in enumerate(INDUSTRIES)
    ]
    product_lines = [
        {"product_line_id": i + 1, "product_line_name": name}
        for i, name in enumerate(PRODUCT_LINES)
    ]
    pl_id = {pl["product_line_name"]: pl["product_line_id"] for pl in product_lines}
    products = [
        {
            "product_id": i + 1,
            "product_name": name,
            "product_line_id": pl_id[line],
            "list_price": price,
        }
        for i, (name, line, price) in enumerate(PRODUCTS)
    ]

    dates: list[dict[str, Any]] = []
    cursor = date(2025, 1, 1)
    while cursor <= date(2026, 12, 31):
        dates.append(
            {
                "date_key": int(cursor.strftime("%Y%m%d")),
                "stat_date": cursor,
                "year": cursor.year,
                "quarter": (cursor.month - 1) // 3 + 1,
                "month": cursor.month,
            }
        )
        cursor += timedelta(days=1)

    return {
        "dw_dim_org": orgs,
        "dw_dim_industry": industries,
        "dw_dim_product_line": product_lines,
        "dw_dim_product": products,
        "dw_dim_date": dates,
    }


# ---------------------------------------------------------------- 事实


def build_facts(dims: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(SEED)
    orgs = dims["dw_dim_org"]
    industries = dims["dw_dim_industry"]
    products = dims["dw_dim_product"]
    lines = {pl["product_line_id"]: pl["product_line_name"] for pl in dims["dw_dim_product_line"]}
    ind_weight_sum = sum(INDUSTRY_WEIGHT.values())
    pl_weight_sum = sum(PRODUCT_LINE_WEIGHT.values())

    revenue_rows: list[dict[str, Any]] = []
    # 同一条产品线下有多个型号，产品线权重需要按型号数摊分，
    # 否则每个型号都按整条产品线的权重计一次，总额会被放大到「型号数」倍。
    line_product_count: dict[str, int] = {}
    for prod in products:
        line_name = lines[prod["product_line_id"]]
        line_product_count[line_name] = line_product_count.get(line_name, 0) + 1

    # 2026 年每月盘子 = base × 该月季节性占比；2025 同步金额除以同比系数，便于算同比
    for org in orgs:
        name = org["org_name"]
        base = ORG_BASE_REVENUE[name]
        growth = ORG_GROWTH[name]
        for year in (2025, 2026):
            season = SEASON_ALL if year == 2025 else SEASON_1_9
            months = range(1, 13) if year == 2025 else range(1, DATA_CUTOFF_MONTH_2026 + 1)
            year_total = base / growth if year == 2025 else base
            for month in months:
                month_budget = year_total * season[month - 1]
                for ind in industries:
                    iw = INDUSTRY_WEIGHT[ind["industry_name"]]
                    for prod in products:
                        pl_name = lines[prod["product_line_id"]]
                        pw = PRODUCT_LINE_WEIGHT[pl_name] / line_product_count[pl_name]
                        weight = iw * pw / (ind_weight_sum * pl_weight_sum)
                        amount = month_budget * weight * _jitter(rng, 0.82, 1.18)
                        revenue_rows.append(
                            {
                                "stat_date": date(year, month, 15),
                                "year": year,
                                "quarter": (month - 1) // 3 + 1,
                                "month": month,
                                "org_id": org["org_id"],
                                "industry_id": ind["industry_id"],
                                "product_id": prod["product_id"],
                                "revenue": round(amount, 2),
                                "contract_amount": round(amount * _jitter(rng, 1.03, 1.22), 2),
                                "collection_amount": round(amount * _jitter(rng, 0.74, 0.97), 2),
                                "order_count": max(
                                    1,
                                    round(amount / PRODUCT_LINE_ORDER_PRICE[pl_name] * _jitter(rng, 0.7, 1.3)),
                                ),
                            }
                        )

    pl_ids = {pl["product_line_name"]: pl["product_line_id"] for pl in dims["dw_dim_product_line"]}
    target_rows: list[dict[str, Any]] = []
    for org in orgs:
        name = org["org_name"]
        for year in (2025, 2026):
            year_target = ORG_BIZ_TARGET[name] * (0.90 if year == 2025 else 1.0)
            for pl_name, weight in PRODUCT_LINE_WEIGHT.items():
                biz = round(year_target * weight / pl_weight_sum, 1)
                sol = round(biz * SOL_TARGET_RATIO * _jitter(rng, 0.94, 1.06), 1)
                target_rows.append(
                    {
                        "year": year,
                        "org_id": org["org_id"],
                        "product_line_id": pl_ids[pl_name],
                        "biz_target": biz,
                        "sol_target": sol,
                    }
                )

    ind_ids = {i["industry_name"]: i["industry_id"] for i in industries}
    org_ids = {o["org_name"]: o["org_id"] for o in orgs}
    risk_rows: list[dict[str, Any]] = []
    for i, (pname, industry, level, rtype, amount, status) in enumerate(RISK_PROJECTS):
        risk_rows.append(
            {
                "project_name": pname,
                "org_id": org_ids[RISK_PROJECT_ORGS[i]],
                "industry_id": ind_ids[industry],
                "risk_level": level,
                "risk_type": rtype,
                "amount": amount,
                "status": status,
                "created_date": date(2026, 1 + (i % 8), 1 + (i % 27)),
            }
        )

    return {
        "dw_fact_revenue": revenue_rows,
        "dw_fact_target": target_rows,
        "dw_fact_project_risk": risk_rows,
    }


# ---------------------------------------------------------------- 元数据


def build_meta(dims: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    tables: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    column_metrics: list[dict[str, Any]] = []

    for spec in TABLE_SPECS:
        tables.append(
            {
                "table_name": spec.table_name,
                "table_comment": spec.table_comment,
                "table_role": spec.table_role,
                "business_domain": spec.business_domain,
                "priority": spec.priority,
            }
        )
        for col in spec.columns:
            columns.append(
                {
                    "table_name": spec.table_name,
                    "column_name": col.name,
                    "data_type": col.data_type,
                    "column_comment": col.comment,
                    "semantic_role": col.role,
                    "synonyms": json.dumps(list(col.synonyms), ensure_ascii=False),
                    "is_primary": col.is_primary,
                }
            )
    for spec in METRIC_SPECS:
        metrics.append(
            {
                "metric_name": spec.metric_name,
                "aliases": json.dumps(list(spec.aliases), ensure_ascii=False),
                "description": spec.description,
                "formula": spec.formula,
                "unit": spec.unit,
                "metric_type": spec.metric_type,
                "relevant_columns": json.dumps(
                    [f"{t}.{c}" for t, c in spec.relevant_columns], ensure_ascii=False
                ),
            }
        )
        for table_name, column_name in spec.relevant_columns:
            column_metrics.append(
                {
                    "table_name": table_name,
                    "column_name": column_name,
                    "metric_name": spec.metric_name,
                }
            )

    # 字段取值字典：从真实维度数据派生，保证「问到的值」一定能查到
    values: list[dict[str, Any]] = []

    def add_values(table: str, column: str, items: list[tuple[str, str, tuple[str, ...]]]) -> None:
        for value, desc, synonyms in items:
            values.append(
                {
                    "table_name": table,
                    "column_name": column,
                    "value": value,
                    "value_desc": desc,
                    "synonyms": json.dumps(list(synonyms), ensure_ascii=False),
                }
            )

    add_values(
        "dw_dim_org",
        "org_name",
        [
            (
                o["org_name"],
                f"{o['region']}大区 · {o['org_level']}",
                (o["org_name"].replace("代表处", "").replace("办事处", ""),),
            )
            for o in dims["dw_dim_org"]
        ],
    )
    add_values(
        "dw_dim_industry",
        "industry_name",
        [(i["industry_name"], i["industry_group"], ()) for i in dims["dw_dim_industry"]],
    )
    add_values(
        "dw_dim_product_line",
        "product_line_name",
        [(p["product_line_name"], "", ()) for p in dims["dw_dim_product_line"]],
    )
    add_values(
        "dw_dim_product",
        "product_name",
        [(p["product_name"], f"单价 {p['list_price']} 万元", ()) for p in dims["dw_dim_product"]],
    )
    regions = sorted({o["region"] for o in dims["dw_dim_org"]})
    add_values("dw_dim_org", "region", [(r, "大区", ()) for r in regions])
    add_values(
        "dw_dim_org",
        "org_level",
        [(lvl, "组织层级", ()) for lvl in ["系统部", "代表处", "办事处"]],
    )
    risk_types = sorted({r[3] for r in RISK_PROJECTS})
    add_values("dw_fact_project_risk", "risk_level", [(v, "风险等级", ()) for v in ["高", "中", "低"]])
    add_values("dw_fact_project_risk", "risk_type", [(v, "风险类型", ()) for v in risk_types])
    add_values(
        "dw_fact_project_risk",
        "status",
        [(v, "处理状态", ()) for v in sorted({r[5] for r in RISK_PROJECTS})],
    )
    add_values(
        "dw_fact_revenue",
        "year",
        [("2026", "当年（1-9 月）", ("今年", "本年")), ("2025", "上年", ("去年",))],
    )

    question_sql = [
        {
            "question": e.question,
            "sql": e.sql,
            "tables_used": json.dumps(list(e.tables_used), ensure_ascii=False),
            "tags": json.dumps(list(e.tags), ensure_ascii=False),
            "intent": e.intent,
            "difficulty": e.difficulty,
        }
        for e in QA_EXAMPLES
    ]

    return {
        "meta_table": tables,
        "meta_column": columns,
        "meta_metric": metrics,
        "meta_column_metric": column_metrics,
        "meta_value": values,
        "meta_question_sql": question_sql,
    }


# ---------------------------------------------------------------- 落库


async def seed_database(database, reset: bool = True) -> dict[str, int]:
    """把维度、事实、元数据写入数据库，返回各表行数。"""
    from app.models import biz, dw, meta  # noqa: F401  触发注册
    from app.db.base import Base

    dims = build_dims()
    facts = build_facts(dims)
    meta_rows = build_meta(dims)

    payload: dict[str, list[dict[str, Any]]] = {**dims, **facts, **meta_rows}
    counts: dict[str, int] = {}

    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if reset:
            # 反向删除，避免外键顺序问题
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(delete(table))
        for table_name, rows in payload.items():
            table = Base.metadata.tables[table_name]
            for chunk in _chunks(rows, 2000):
                await conn.execute(insert(table), chunk)
            counts[table_name] = len(rows)
    return counts


def _chunks(rows: list[dict[str, Any]], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]
