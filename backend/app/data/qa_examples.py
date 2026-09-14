"""自然语言 ↔ SQL 样例库。

同时服务三个目的：
1. 作为 LLM 的 few-shot 示例，显著降低「表选错、join 错、fan-out」的概率；
2. 作为规则引擎（离线兜底）的意图路由依据（`intent` 字段）；
3. 作为回归评测集的种子（`tests/test_pipeline.py` 会用其中一部分直接验证）。

SQL 统一使用双引号中文别名（SQLite 原生支持），执行前会按目标方言转换。
"""

from typing import NamedTuple


class QaExample(NamedTuple):
    question: str
    sql: str
    tables_used: tuple[str, ...]
    tags: tuple[str, ...]
    intent: str
    difficulty: str = "easy"
    note: str = ""


QA_EXAMPLES: tuple[QaExample, ...] = (
    QaExample(
        "2026年各经营单元的收入排名",
        """SELECT o.org_name AS "经营单元", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = 2026
GROUP BY o.org_name
ORDER BY "收入额" DESC
LIMIT 10""",
        ("dw_fact_revenue", "dw_dim_org"),
        ("收入", "经营单元", "排名"),
        "org_revenue_rank",
    ),
    QaExample(
        "2026年各经营单元的收入和完成率分别是多少",
        # 收入与目标粒度不同（目标按产品线拆分），先各自聚合再 join，避免 fan-out 导致收入被放大
        """SELECT rev.org_name AS "经营单元", rev.revenue AS "收入额",
       tgt.biz_target AS "商业目标",
       ROUND(rev.revenue / tgt.biz_target * 100, 1) AS "完成率"
FROM (
    SELECT o.org_name AS org_name, SUM(r.revenue) AS revenue
    FROM dw_fact_revenue r JOIN dw_dim_org o ON r.org_id = o.org_id
    WHERE r.year = 2026 GROUP BY o.org_name
) rev
JOIN (
    SELECT o.org_name AS org_name, SUM(t.biz_target) AS biz_target
    FROM dw_fact_target t JOIN dw_dim_org o ON t.org_id = o.org_id
    WHERE t.year = 2026 GROUP BY o.org_name
) tgt ON rev.org_name = tgt.org_name
ORDER BY "完成率" DESC""",
        ("dw_fact_revenue", "dw_fact_target", "dw_dim_org"),
        ("收入", "完成率", "经营单元"),
        "org_target_rate",
        "hard",
        "两个事实表粒度不同，必须分别聚合后再 join",
    ),
    QaExample(
        "2026年商业目标TOP5的经营单元，对比商解目标",
        """SELECT o.org_name AS "经营单元", SUM(t.biz_target) AS "商业目标",
       SUM(t.sol_target) AS "商解目标"
FROM dw_fact_target t
JOIN dw_dim_org o ON t.org_id = o.org_id
WHERE t.year = 2026
GROUP BY o.org_name
ORDER BY "商业目标" DESC
LIMIT 5""",
        ("dw_fact_target", "dw_dim_org"),
        ("商业目标", "商解目标", "TOP5"),
        "org_target_compare",
    ),
    QaExample(
        "2026年各行业的收入是多少",
        """SELECT i.industry_name AS "行业", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_industry i ON r.industry_id = i.industry_id
WHERE r.year = 2026
GROUP BY i.industry_name
ORDER BY "收入额" DESC""",
        ("dw_fact_revenue", "dw_dim_industry"),
        ("行业", "收入"),
        "industry_revenue",
    ),
    QaExample(
        "政企行业收入在3000万到5000万之间的经营单元",
        """SELECT o.org_name AS "经营单元", i.industry_name AS "行业", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
JOIN dw_dim_industry i ON r.industry_id = i.industry_id
WHERE r.year = 2026 AND i.industry_name = '数字政府'
GROUP BY o.org_name, i.industry_name
HAVING SUM(r.revenue) BETWEEN 3000 AND 5000
ORDER BY "收入额" DESC""",
        ("dw_fact_revenue", "dw_dim_org", "dw_dim_industry"),
        ("行业", "区间筛选", "经营单元"),
        "industry_filter",
        "hard",
        "金额区间过滤作用在聚合结果上，应使用 HAVING",
    ),
    QaExample(
        "2026年各产品线的收入占比",
        """SELECT pl.product_line_name AS "产品线", SUM(r.revenue) AS "收入额",
       ROUND(SUM(r.revenue) * 100.0 / (SELECT SUM(revenue) FROM dw_fact_revenue WHERE year = 2026), 1) AS "占比"
FROM dw_fact_revenue r
JOIN dw_dim_product p ON r.product_id = p.product_id
JOIN dw_dim_product_line pl ON p.product_line_id = pl.product_line_id
WHERE r.year = 2026
GROUP BY pl.product_line_name
ORDER BY "收入额" DESC""",
        ("dw_fact_revenue", "dw_dim_product", "dw_dim_product_line"),
        ("产品线", "收入", "占比"),
        "product_line_revenue",
    ),
    QaExample(
        "2026年销售最好的3个产品型号",
        """SELECT p.product_name AS "产品型号", pl.product_line_name AS "产品线",
       SUM(r.revenue) AS "销售额", SUM(r.order_count) AS "订单数"
FROM dw_fact_revenue r
JOIN dw_dim_product p ON r.product_id = p.product_id
JOIN dw_dim_product_line pl ON p.product_line_id = pl.product_line_id
WHERE r.year = 2026
GROUP BY p.product_name, pl.product_line_name
ORDER BY "销售额" DESC
LIMIT 3""",
        ("dw_fact_revenue", "dw_dim_product", "dw_dim_product_line"),
        ("产品型号", "TOP3", "销售额"),
        "product_top",
    ),
    QaExample(
        "2026年每月的合同金额趋势",
        """SELECT r.month AS "月份", SUM(r.contract_amount) AS "合同额", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
WHERE r.year = 2026
GROUP BY r.month
ORDER BY r.month""",
        ("dw_fact_revenue",),
        ("月度趋势", "合同额"),
        "monthly_trend",
    ),
    QaExample(
        "2025年和2026年1-9月各产品线的同比变化",
        """SELECT pl.product_line_name AS "产品线",
       SUM(CASE WHEN r.year = 2026 THEN r.revenue ELSE 0 END) AS "本期收入",
       SUM(CASE WHEN r.year = 2025 THEN r.revenue ELSE 0 END) AS "上年同期收入",
       ROUND((SUM(CASE WHEN r.year = 2026 THEN r.revenue ELSE 0 END)
              - SUM(CASE WHEN r.year = 2025 THEN r.revenue ELSE 0 END)) * 100.0
             / NULLIF(SUM(CASE WHEN r.year = 2025 THEN r.revenue ELSE 0 END), 0), 1) AS "同比增幅"
FROM dw_fact_revenue r
JOIN dw_dim_product p ON r.product_id = p.product_id
JOIN dw_dim_product_line pl ON p.product_line_id = pl.product_line_id
WHERE r.month <= 9
GROUP BY pl.product_line_name
ORDER BY "同比增幅" DESC""",
        ("dw_fact_revenue", "dw_dim_product", "dw_dim_product_line"),
        ("同比", "产品线", "趋势"),
        "yoy_trend",
        "hard",
        "为保证可比，两年都截取 1-9 月",
    ),
    QaExample(
        "目前有多少个高风险项目",
        """SELECT COUNT(*) AS "高风险项目数", ROUND(SUM(amount), 1) AS "风险金额"
FROM dw_fact_project_risk
WHERE risk_level = '高'""",
        ("dw_fact_project_risk",),
        ("风险", "数量"),
        "risk_count",
    ),
    QaExample(
        "高风险项目有哪些",
        """SELECT pr.project_name AS "项目名称", o.org_name AS "经营单元",
       i.industry_name AS "行业", pr.risk_type AS "风险类型",
       pr.amount AS "风险金额", pr.status AS "状态"
FROM dw_fact_project_risk pr
JOIN dw_dim_org o ON pr.org_id = o.org_id
JOIN dw_dim_industry i ON pr.industry_id = i.industry_id
WHERE pr.risk_level = '高'
ORDER BY pr.amount DESC""",
        ("dw_fact_project_risk", "dw_dim_org", "dw_dim_industry"),
        ("风险", "明细"),
        "risk_list",
    ),
    QaExample(
        "北京代表处今年的达成情况",
        """SELECT o.org_name AS "经营单元", r.year AS "年份", SUM(r.revenue) AS "收入额",
       SUM(r.collection_amount) AS "回款额", SUM(r.order_count) AS "订单数"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE o.org_name = '北京代表处'
GROUP BY o.org_name, r.year
ORDER BY r.year""",
        ("dw_fact_revenue", "dw_dim_org"),
        ("经营单元", "达成", "明细"),
        "org_detail",
    ),
    QaExample(
        "2026年各大区的收入情况",
        """SELECT o.region AS "大区", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = 2026
GROUP BY o.region
ORDER BY "收入额" DESC""",
        ("dw_fact_revenue", "dw_dim_org"),
        ("大区", "收入"),
        "region_revenue",
    ),
    QaExample(
        "2026年各经营单元的回款率排名",
        """SELECT o.org_name AS "经营单元", SUM(r.revenue) AS "收入额",
       SUM(r.collection_amount) AS "回款额",
       ROUND(SUM(r.collection_amount) / SUM(r.revenue) * 100, 1) AS "回款率"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = 2026
GROUP BY o.org_name
ORDER BY "回款率" ASC
LIMIT 10""",
        ("dw_fact_revenue", "dw_dim_org"),
        ("回款率", "经营单元"),
        "collection_rate",
    ),
    QaExample(
        "2026年各行业的订单数",
        """SELECT i.industry_name AS "行业", SUM(r.order_count) AS "订单数"
FROM dw_fact_revenue r
JOIN dw_dim_industry i ON r.industry_id = i.industry_id
WHERE r.year = 2026
GROUP BY i.industry_name
ORDER BY "订单数" DESC""",
        ("dw_fact_revenue", "dw_dim_industry"),
        ("订单数", "行业"),
        "order_count",
    ),
    QaExample(
        "2025年各季度的收入是多少",
        """SELECT r.year AS "年份", r.quarter AS "季度", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
WHERE r.year = 2025
GROUP BY r.year, r.quarter
ORDER BY r.quarter""",
        ("dw_fact_revenue",),
        ("季度", "收入"),
        "quarterly_revenue",
    ),
    QaExample(
        "各组织层级的收入对比",
        """SELECT o.org_level AS "组织层级", COUNT(DISTINCT o.org_id) AS "单元数",
       SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = 2026
GROUP BY o.org_level
ORDER BY "收入额" DESC""",
        ("dw_fact_revenue", "dw_dim_org"),
        ("组织层级", "收入"),
        "org_level_revenue",
    ),
    QaExample(
        "2026年各产品线的商业目标和商解目标",
        """SELECT pl.product_line_name AS "产品线", SUM(t.biz_target) AS "商业目标",
       SUM(t.sol_target) AS "商解目标"
FROM dw_fact_target t
JOIN dw_dim_product_line pl ON t.product_line_id = pl.product_line_id
WHERE t.year = 2026
GROUP BY pl.product_line_name
ORDER BY "商业目标" DESC""",
        ("dw_fact_target", "dw_dim_product_line"),
        ("产品线", "目标"),
        "product_line_target",
    ),
    QaExample(
        "项目风险按类型分布情况",
        """SELECT risk_type AS "风险类型", COUNT(*) AS "项目数", ROUND(SUM(amount), 1) AS "风险金额"
FROM dw_fact_project_risk
GROUP BY risk_type
ORDER BY "风险金额" DESC""",
        ("dw_fact_project_risk",),
        ("风险", "类型分布"),
        "risk_by_type",
    ),
    QaExample(
        "2026年1-9月各经营单元收入同比",
        """SELECT o.org_name AS "经营单元",
       SUM(CASE WHEN r.year = 2026 THEN r.revenue ELSE 0 END) AS "本期收入",
       SUM(CASE WHEN r.year = 2025 THEN r.revenue ELSE 0 END) AS "上年同期收入"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.month <= 9
GROUP BY o.org_name
ORDER BY "本期收入" DESC
LIMIT 10""",
        ("dw_fact_revenue", "dw_dim_org"),
        ("同比", "经营单元"),
        "org_yoy",
    ),
)


# 意图 → 样例，规则引擎按此路由
EXAMPLES_BY_INTENT: dict[str, list[QaExample]] = {}
for _e in QA_EXAMPLES:
    EXAMPLES_BY_INTENT.setdefault(_e.intent, []).append(_e)
