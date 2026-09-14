"""规则引擎 SQL 生成器（离线兜底 / 确定性路径）。

它的价值不止是「没 Key 时能演示」：
- 单测可以完全不依赖网络，断言「问题 → SQL → 结果」的完整链路；
- 作为大模型的**对照组**：线上把两者结果做 diff，可以持续发现模型退化；
- 覆盖问数场景里最高频的十几种问法，命中时比大模型更快、更省钱。

实现方式：意图识别 + 槽位抽取 + SQL 模板渲染，全部可解释。
"""

import re
from dataclasses import dataclass, field

from app.entities import MetaSnapshot

# 业务口语 → 标准枚举值
INDUSTRY_ALIASES = {
    "政企": "数字政府",
    "政务": "数字政府",
    "政府": "数字政府",
    "银行": "金融",
    "券商": "金融",
    "运营商": "互联网",
    "制造": "智能制造",
    "能源": "电力",
    "军工": "JDJG",
    "军警": "JDJG",
}
PRODUCT_LINE_ALIASES = {
    "通用": "通用计算",
    "智算": "智能计算",
    "智能": "智能计算",
    "商解": "商业解决方案",
    "解决方案": "商业解决方案",
}

DEFAULT_YEAR = 2026
CURRENT_YEAR = 2026

_YEAR_RE = re.compile(r"(20\d{2})")
_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*万?\s*(?:到|至|~|—|－|-|—)\s*(\d+(?:\.\d+)?)")
_TOP_RE = re.compile(r"(?:top|前)\s*(\d+)", re.IGNORECASE)
_BEST_RE = re.compile(r"(?:最好|最多|最高|最大|前)\s*的?\s*(\d+)\s*个")
_COUNT_RE = re.compile(r"(\d+)\s*个(?:产品|型号|经营单元|代表处|办事处)")


@dataclass
class Slots:
    year: int = DEFAULT_YEAR
    # 只有问题里明确出现「TOP5 / 前3 / 最好的3个」时才限制行数；
    # 否则保持 None，让「各经营单元」「各行业」这类问题返回全集，
    # 最终由 SQL 安全网关统一兜底一个安全上限。
    limit: int | None = None
    org: str | None = None
    industry: str | None = None
    product_line: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    requested_count: int | None = None
    years: list[int] = field(default_factory=list)


@dataclass
class RuleSql:
    sql: str
    intent: str
    slots: Slots
    confidence: float = 0.6
    reason: str = ""


def extract_slots(question: str, snapshot: MetaSnapshot) -> Slots:
    q = question or ""
    slots = Slots()

    years = [int(y) for y in _YEAR_RE.findall(q)]
    slots.years = years
    if years:
        slots.year = years[-1]

    rng = _RANGE_RE.search(q)
    if rng:
        low, high = float(rng.group(1)), float(rng.group(2))
        slots.amount_min, slots.amount_max = min(low, high), max(low, high)

    top = _TOP_RE.search(q) or _BEST_RE.search(q) or _COUNT_RE.search(q)
    if top:
        slots.requested_count = int(top.group(1))
        slots.limit = slots.requested_count

    text = q.lower()
    for value in snapshot.values:
        low = value.value.lower()
        synonyms = [s.lower() for s in value.synonyms]
        if value.column_name == "org_name":
            if low in text or any(s and s in text for s in synonyms):
                slots.org = value.value
        elif value.column_name == "industry_name":
            if low in text:
                slots.industry = value.value
        elif value.column_name == "product_line_name" and low in text:
            slots.product_line = value.value

    if slots.industry is None:
        for alias, standard in INDUSTRY_ALIASES.items():
            if alias in q:
                slots.industry = standard
                break
    if slots.product_line is None:
        for alias, standard in PRODUCT_LINE_ALIASES.items():
            if alias in q:
                slots.product_line = standard
                break
    return slots


def detect_intent(question: str, slots: Slots) -> str:
    q = question or ""
    has = lambda *words: any(w in q for w in words)  # noqa: E731

    # 「按类型/分布」要先于「清单/计数」判断：
    # 「项目风险按类型分布情况」同时命中「项目风险」和「分布」，
    # 若先判清单会被误判成 risk_list。
    if has("风险") and has("类型", "分布", "分类"):
        return "risk_by_type"
    if has("风险") and has("高风险", "风险项目", "项目风险"):
        return "risk_count" if has("多少", "几个", "数量", "多少个", "统计") else "risk_list"
    if has("风险") and not has("项目"):
        return "risk_count"
    if has("同比", "同期", "增长", "下滑", "变化"):
        return "yoy_trend" if has("产品线") else "org_yoy"
    if has("完成率", "达成率"):
        return "org_target_rate"
    if has("回款"):
        return "collection_rate"
    if has("组织层级", "层级"):
        return "org_level_revenue"
    if has("大区", "区域", "地区"):
        return "region_revenue"
    if has("季度"):
        return "quarterly_revenue"
    if has("订单"):
        return "order_count"
    if has("产品线") and has("目标") and not has("收入", "回款"):
        return "product_line_target"
    if has("产品线") and has("占比", "收入", "销售额", "营收"):
        return "product_line_revenue"
    if (has("型号", "产品") and has("销售", "卖出", "top", "最好", "最多", "排名")) or (
        has("型号") and slots.requested_count
    ):
        return "product_top"
    if has("行业") and (slots.amount_min is not None or has("之间", "区间", "范围")):
        return "industry_filter"
    if has("行业"):
        return "industry_revenue"
    if has("每月", "趋势", "月度") and has("合同", "合同额", "合同金额"):
        return "monthly_trend"
    if has("每月", "趋势", "月度", "逐月"):
        return "monthly_trend"
    if has("目标") and (has("商业目标", "商解目标") or has("top", "最高", "前几")):
        return "org_target_compare"
    if slots.org and has("达成", "情况", "怎么样", "如何", "表现"):
        return "org_detail"
    if has("排名", "top", "最高", "最多", "排行"):
        return "org_revenue_rank"
    if has("收入", "销售额", "营收", "业绩"):
        return "org_revenue_rank"
    return "org_revenue_rank"


# ------------------------------------------------------------------ 模板


def _limit_clause(s: Slots, default: int | None = None) -> str:
    """按需拼接 LIMIT：问题里给了 N 就用 N，否则用 default，都没有就不加。

    不加 LIMIT 时由安全网关补齐安全上限，因此这里绝不硬编码一个会把
    「各经营单元」截断成 10 条的魔数。
    """
    limit = s.limit if s.limit is not None else default
    return f"\nLIMIT {limit}" if limit else ""


def _org_revenue_rank(s: Slots) -> str:
    return f"""SELECT o.org_name AS "经营单元", SUM(r.revenue) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = {s.year}
GROUP BY o.org_name
ORDER BY "收入额" DESC{_limit_clause(s)}"""


def _org_target_rate(s: Slots) -> str:
    return f"""SELECT rev.org_name AS "经营单元", ROUND(rev.revenue, 1) AS "收入额",
       ROUND(tgt.biz_target, 1) AS "商业目标",
       ROUND(rev.revenue / NULLIF(tgt.biz_target, 0) * 100, 1) AS "完成率"
FROM (
    SELECT o.org_name AS org_name, SUM(r.revenue) AS revenue
    FROM dw_fact_revenue r JOIN dw_dim_org o ON r.org_id = o.org_id
    WHERE r.year = {s.year} GROUP BY o.org_name
) rev
JOIN (
    SELECT o.org_name AS org_name, SUM(t.biz_target) AS biz_target
    FROM dw_fact_target t JOIN dw_dim_org o ON t.org_id = o.org_id
    WHERE t.year = {s.year} GROUP BY o.org_name
) tgt ON rev.org_name = tgt.org_name
ORDER BY "完成率" DESC{_limit_clause(s)}"""


def _org_target_compare(s: Slots) -> str:
    return f"""SELECT o.org_name AS "经营单元", ROUND(SUM(t.biz_target), 1) AS "商业目标",
       ROUND(SUM(t.sol_target), 1) AS "商解目标"
FROM dw_fact_target t
JOIN dw_dim_org o ON t.org_id = o.org_id
WHERE t.year = {s.year}
GROUP BY o.org_name
ORDER BY "商业目标" DESC{_limit_clause(s, default=5)}"""


def _industry_revenue(s: Slots) -> str:
    return f"""SELECT i.industry_name AS "行业", ROUND(SUM(r.revenue), 1) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_industry i ON r.industry_id = i.industry_id
WHERE r.year = {s.year}
GROUP BY i.industry_name
ORDER BY "收入额" DESC{_limit_clause(s)}"""


def _industry_filter(s: Slots) -> str:
    industry = s.industry or "数字政府"
    low = s.amount_min if s.amount_min is not None else 0
    high = s.amount_max if s.amount_max is not None else 1000000
    return f"""SELECT o.org_name AS "经营单元", i.industry_name AS "行业", ROUND(SUM(r.revenue), 1) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
JOIN dw_dim_industry i ON r.industry_id = i.industry_id
WHERE r.year = {s.year} AND i.industry_name = '{industry}'
GROUP BY o.org_name, i.industry_name
HAVING SUM(r.revenue) BETWEEN {low} AND {high}
ORDER BY "收入额" DESC{_limit_clause(s)}"""


def _product_line_revenue(s: Slots) -> str:
    return f"""SELECT pl.product_line_name AS "产品线", ROUND(SUM(r.revenue), 1) AS "收入额",
       ROUND(SUM(r.revenue) * 100.0 / (SELECT SUM(revenue) FROM dw_fact_revenue WHERE year = {s.year}), 1) AS "占比"
FROM dw_fact_revenue r
JOIN dw_dim_product p ON r.product_id = p.product_id
JOIN dw_dim_product_line pl ON p.product_line_id = pl.product_line_id
WHERE r.year = {s.year}
GROUP BY pl.product_line_name
ORDER BY "收入额" DESC"""


def _product_top(s: Slots) -> str:
    return f"""SELECT p.product_name AS "产品型号", pl.product_line_name AS "产品线",
       ROUND(SUM(r.revenue), 1) AS "销售额", SUM(r.order_count) AS "订单数"
FROM dw_fact_revenue r
JOIN dw_dim_product p ON r.product_id = p.product_id
JOIN dw_dim_product_line pl ON p.product_line_id = pl.product_line_id
WHERE r.year = {s.year}
GROUP BY p.product_name, pl.product_line_name
ORDER BY "销售额" DESC{_limit_clause(s, default=3)}"""


def _monthly_trend(s: Slots) -> str:
    return f"""SELECT r.month AS "月份", ROUND(SUM(r.contract_amount), 1) AS "合同额",
       ROUND(SUM(r.revenue), 1) AS "收入额"
FROM dw_fact_revenue r
WHERE r.year = {s.year}
GROUP BY r.month
ORDER BY r.month"""


def _yoy_trend(s: Slots) -> str:
    cur = s.years[-1] if s.years else DEFAULT_YEAR
    prev = s.years[0] if len(s.years) > 1 else cur - 1
    pl_filter = (
        f"WHERE pl.product_line_name = '{s.product_line}' AND r.month <= 9"
        if s.product_line
        else "WHERE r.month <= 9"
    )
    return f"""SELECT pl.product_line_name AS "产品线",
       ROUND(SUM(CASE WHEN r.year = {cur} THEN r.revenue ELSE 0 END), 1) AS "本期收入",
       ROUND(SUM(CASE WHEN r.year = {prev} THEN r.revenue ELSE 0 END), 1) AS "上年同期收入",
       ROUND((SUM(CASE WHEN r.year = {cur} THEN r.revenue ELSE 0 END)
              - SUM(CASE WHEN r.year = {prev} THEN r.revenue ELSE 0 END)) * 100.0
             / NULLIF(SUM(CASE WHEN r.year = {prev} THEN r.revenue ELSE 0 END), 0), 1) AS "同比增幅"
FROM dw_fact_revenue r
JOIN dw_dim_product p ON r.product_id = p.product_id
JOIN dw_dim_product_line pl ON p.product_line_id = pl.product_line_id
{pl_filter}
GROUP BY pl.product_line_name
ORDER BY "同比增幅" DESC"""


def _risk_count(s: Slots) -> str:
    return """SELECT COUNT(*) AS "高风险项目数", ROUND(SUM(amount), 1) AS "风险金额"
FROM dw_fact_project_risk
WHERE risk_level = '高'"""


def _risk_list(s: Slots) -> str:
    return f"""SELECT pr.project_name AS "项目名称", o.org_name AS "经营单元",
       i.industry_name AS "行业", pr.risk_type AS "风险类型",
       ROUND(pr.amount, 1) AS "风险金额", pr.status AS "状态"
FROM dw_fact_project_risk pr
JOIN dw_dim_org o ON pr.org_id = o.org_id
JOIN dw_dim_industry i ON pr.industry_id = i.industry_id
WHERE pr.risk_level = '高'
ORDER BY pr.amount DESC{_limit_clause(s)}"""


def _risk_by_type(s: Slots) -> str:
    return """SELECT risk_type AS "风险类型", COUNT(*) AS "项目数", ROUND(SUM(amount), 1) AS "风险金额"
FROM dw_fact_project_risk
GROUP BY risk_type
ORDER BY "风险金额" DESC"""


def _org_detail(s: Slots) -> str:
    org = s.org or "北京代表处"
    return f"""SELECT o.org_name AS "经营单元", r.year AS "年份", ROUND(SUM(r.revenue), 1) AS "收入额",
       ROUND(SUM(r.collection_amount), 1) AS "回款额", SUM(r.order_count) AS "订单数"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE o.org_name = '{org}'
GROUP BY o.org_name, r.year
ORDER BY r.year"""


def _region_revenue(s: Slots) -> str:
    return f"""SELECT o.region AS "大区", ROUND(SUM(r.revenue), 1) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = {s.year}
GROUP BY o.region
ORDER BY "收入额" DESC"""


def _collection_rate(s: Slots) -> str:
    return f"""SELECT o.org_name AS "经营单元", ROUND(SUM(r.revenue), 1) AS "收入额",
       ROUND(SUM(r.collection_amount), 1) AS "回款额",
       ROUND(SUM(r.collection_amount) / NULLIF(SUM(r.revenue), 0) * 100, 1) AS "回款率"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = {s.year}
GROUP BY o.org_name
ORDER BY "回款率" ASC{_limit_clause(s)}"""


def _order_count(s: Slots) -> str:
    return f"""SELECT i.industry_name AS "行业", SUM(r.order_count) AS "订单数"
FROM dw_fact_revenue r
JOIN dw_dim_industry i ON r.industry_id = i.industry_id
WHERE r.year = {s.year}
GROUP BY i.industry_name
ORDER BY "订单数" DESC{_limit_clause(s)}"""


def _quarterly_revenue(s: Slots) -> str:
    return f"""SELECT r.year AS "年份", r.quarter AS "季度", ROUND(SUM(r.revenue), 1) AS "收入额"
FROM dw_fact_revenue r
WHERE r.year = {s.year}
GROUP BY r.year, r.quarter
ORDER BY r.quarter"""


def _org_level_revenue(s: Slots) -> str:
    return f"""SELECT o.org_level AS "组织层级", COUNT(DISTINCT o.org_id) AS "单元数",
       ROUND(SUM(r.revenue), 1) AS "收入额"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.year = {s.year}
GROUP BY o.org_level
ORDER BY "收入额" DESC"""


def _product_line_target(s: Slots) -> str:
    return f"""SELECT pl.product_line_name AS "产品线", ROUND(SUM(t.biz_target), 1) AS "商业目标",
       ROUND(SUM(t.sol_target), 1) AS "商解目标"
FROM dw_fact_target t
JOIN dw_dim_product_line pl ON t.product_line_id = pl.product_line_id
WHERE t.year = {s.year}
GROUP BY pl.product_line_name
ORDER BY "商业目标" DESC"""


def _org_yoy(s: Slots) -> str:
    cur = s.years[-1] if s.years else DEFAULT_YEAR
    prev = s.years[0] if len(s.years) > 1 else cur - 1
    org_filter = f"AND o.org_name = '{s.org}'" if s.org else ""
    return f"""SELECT o.org_name AS "经营单元",
       ROUND(SUM(CASE WHEN r.year = {cur} THEN r.revenue ELSE 0 END), 1) AS "本期收入",
       ROUND(SUM(CASE WHEN r.year = {prev} THEN r.revenue ELSE 0 END), 1) AS "上年同期收入",
       ROUND((SUM(CASE WHEN r.year = {cur} THEN r.revenue ELSE 0 END)
              - SUM(CASE WHEN r.year = {prev} THEN r.revenue ELSE 0 END)) * 100.0
             / NULLIF(SUM(CASE WHEN r.year = {prev} THEN r.revenue ELSE 0 END), 0), 1) AS "同比增幅"
FROM dw_fact_revenue r
JOIN dw_dim_org o ON r.org_id = o.org_id
WHERE r.month <= 9 {org_filter}
GROUP BY o.org_name
ORDER BY "本期收入" DESC{_limit_clause(s)}"""


TEMPLATES: dict[str, tuple] = {
    "org_revenue_rank": (_org_revenue_rank, 0.9),
    "org_target_rate": (_org_target_rate, 0.95),
    "org_target_compare": (_org_target_compare, 0.9),
    "industry_revenue": (_industry_revenue, 0.9),
    "industry_filter": (_industry_filter, 0.85),
    "product_line_revenue": (_product_line_revenue, 0.9),
    "product_top": (_product_top, 0.9),
    "monthly_trend": (_monthly_trend, 0.9),
    "yoy_trend": (_yoy_trend, 0.9),
    "risk_count": (_risk_count, 0.95),
    "risk_list": (_risk_list, 0.9),
    "risk_by_type": (_risk_by_type, 0.9),
    "org_detail": (_org_detail, 0.8),
    "region_revenue": (_region_revenue, 0.9),
    "collection_rate": (_collection_rate, 0.9),
    "order_count": (_order_count, 0.9),
    "quarterly_revenue": (_quarterly_revenue, 0.9),
    "org_level_revenue": (_org_level_revenue, 0.9),
    "product_line_target": (_product_line_target, 0.9),
    "org_yoy": (_org_yoy, 0.9),
}


def generate_with_rules(question: str, snapshot: MetaSnapshot) -> RuleSql:
    """规则引擎入口：问题 → SQL。"""
    slots = extract_slots(question, snapshot)
    intent = detect_intent(question, slots)
    builder, confidence = TEMPLATES.get(intent, (None, 0.0))
    if builder is None:
        intent, builder, confidence = "org_revenue_rank", _org_revenue_rank, 0.5
    sql = builder(slots)
    reason = f"命中意图 {intent}"
    if slots.org:
        reason += f"，经营单元={slots.org}"
    if slots.industry:
        reason += f"，行业={slots.industry}"
    if slots.product_line:
        reason += f"，产品线={slots.product_line}"
    if slots.amount_min is not None:
        reason += f"，金额区间=[{slots.amount_min}, {slots.amount_max}]"
    return RuleSql(sql=sql, intent=intent, slots=slots, confidence=confidence, reason=reason)
