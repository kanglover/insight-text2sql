"""元数据知识库的声明式定义。

把「表/字段/指标」写成声明式结构，好处是：
1. 建库脚本（seed）与检索用的元数据来自同一份事实，不会漂移；
2. 新增字段或指标时只改这里，召回、Prompt、规则引擎自动受益。
"""

from typing import NamedTuple


class ColumnSpec(NamedTuple):
    name: str
    data_type: str
    comment: str
    role: str  # dimension / measure / date / id
    synonyms: tuple[str, ...] = ()
    is_primary: int = 0


class TableSpec(NamedTuple):
    table_name: str
    table_comment: str
    table_role: str  # fact / dim
    business_domain: str
    priority: int
    columns: tuple[ColumnSpec, ...]


class MetricSpec(NamedTuple):
    metric_name: str
    aliases: tuple[str, ...]
    description: str
    formula: str
    unit: str
    metric_type: str  # amount / ratio / count / trend
    relevant_columns: tuple[tuple[str, str], ...]


TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "dw_dim_org",
        "经营单元维度表",
        "dim",
        "组织",
        80,
        (
            ColumnSpec("org_id", "INT", "经营单元ID", "id", ("单元ID",), 1),
            ColumnSpec("org_code", "VARCHAR", "经营单元编码", "id", ("单元编码",)),
            ColumnSpec(
                "org_name", "VARCHAR", "经营单元名称，如北京代表处/江西办事处", "dimension", ("经营单元", "代表处", "办事处", "单元")
            ),
            ColumnSpec("org_level", "VARCHAR", "组织层级：系统部/代表处/办事处", "dimension", ("层级", "组织层级")),
            ColumnSpec("region", "VARCHAR", "所属大区，如华北/华东/华南", "dimension", ("大区", "区域")),
            ColumnSpec("parent_org", "VARCHAR", "上级组织名称", "dimension", ("上级组织",)),
        ),
    ),
    TableSpec(
        "dw_dim_industry",
        "行业维度表",
        "dim",
        "客户",
        70,
        (
            ColumnSpec("industry_id", "INT", "行业ID", "id"),
            ColumnSpec(
                "industry_name",
                "VARCHAR",
                "行业名称，如金融/数字政府/互联网/智能制造",
                "dimension",
                ("行业", "客户行业", "政企行业"),
            ),
            ColumnSpec("industry_group", "VARCHAR", "行业大类，如政府/金融/能源", "dimension", ("行业大类",)),
        ),
    ),
    TableSpec(
        "dw_dim_product_line",
        "产品线维度表",
        "dim",
        "产品",
        65,
        (
            ColumnSpec("product_line_id", "INT", "产品线ID", "id"),
            ColumnSpec(
                "product_line_name",
                "VARCHAR",
                "产品线名称：通用计算/智能计算/商业解决方案",
                "dimension",
                ("产品线", "产品大类", "业务线"),
            ),
        ),
    ),
    TableSpec(
        "dw_dim_product",
        "产品型号维度表",
        "dim",
        "产品",
        60,
        (
            ColumnSpec("product_id", "INT", "产品ID", "id"),
            ColumnSpec("product_name", "VARCHAR", "产品型号名称，如 R5300 G5/卡多多", "dimension", ("产品型号", "型号", "产品")),
            ColumnSpec("product_line_id", "INT", "所属产品线ID", "id"),
            ColumnSpec("list_price", "DECIMAL", "挂牌单价（万元）", "measure", ("单价", "价格")),
        ),
    ),
    TableSpec(
        "dw_dim_date",
        "日期维度表",
        "dim",
        "时间",
        55,
        (
            ColumnSpec("date_key", "INT", "日期主键 yyyymmdd", "id"),
            ColumnSpec("stat_date", "DATE", "统计日期", "date", ("日期",)),
            ColumnSpec("year", "INT", "年份", "date", ("年", "年度")),
            ColumnSpec("quarter", "INT", "季度（1-4）", "date", ("季度", "Q")),
            ColumnSpec("month", "INT", "月份（1-12）", "date", ("月", "月份")),
        ),
    ),
    TableSpec(
        "dw_fact_revenue",
        "收入事实表：按 日期×经营单元×行业×产品 记录收入、合同额、回款与订单数",
        "fact",
        "销售经管",
        100,
        (
            ColumnSpec("id", "INT", "主键", "id"),
            ColumnSpec("stat_date", "DATE", "统计日期", "date", ("日期",)),
            ColumnSpec("year", "INT", "年份", "date", ("年", "年度")),
            ColumnSpec("quarter", "INT", "季度", "date", ("季度",)),
            ColumnSpec("month", "INT", "月份", "date", ("月",)),
            ColumnSpec("org_id", "INT", "经营单元ID，关联 dw_dim_org", "id", ("经营单元",)),
            ColumnSpec("industry_id", "INT", "行业ID，关联 dw_dim_industry", "id", ("行业",)),
            ColumnSpec("product_id", "INT", "产品ID，关联 dw_dim_product", "id", ("产品",)),
            ColumnSpec("revenue", "DECIMAL", "收入额（万元）", "measure", ("收入", "收入额", "销售额", "营收")),
            ColumnSpec("contract_amount", "DECIMAL", "合同额（万元）", "measure", ("合同额", "合同金额", "签约额")),
            ColumnSpec("collection_amount", "DECIMAL", "回款额（万元）", "measure", ("回款", "回款额", "收款")),
            ColumnSpec("order_count", "INT", "订单数", "measure", ("订单数", "订单量", "订单个数")),
        ),
    ),
    TableSpec(
        "dw_fact_target",
        "目标事实表：按 年份×经营单元×产品线 记录商业目标与商解目标",
        "fact",
        "销售经管",
        95,
        (
            ColumnSpec("id", "INT", "主键", "id"),
            ColumnSpec("year", "INT", "年份", "date", ("年", "年度")),
            ColumnSpec("org_id", "INT", "经营单元ID，关联 dw_dim_org", "id", ("经营单元",)),
            ColumnSpec("product_line_id", "INT", "产品线ID，关联 dw_dim_product_line", "id", ("产品线",)),
            ColumnSpec("biz_target", "DECIMAL", "商业目标（万元）", "measure", ("商业目标", "目标")),
            ColumnSpec("sol_target", "DECIMAL", "商解目标（万元）", "measure", ("商解目标",)),
        ),
    ),
    TableSpec(
        "dw_fact_project_risk",
        "项目风险事实表：记录项目风险等级、类型与金额",
        "fact",
        "项目管理",
        50,
        (
            ColumnSpec("id", "INT", "主键", "id"),
            ColumnSpec("project_name", "VARCHAR", "项目名称", "dimension", ("项目", "项目名称")),
            ColumnSpec("org_id", "INT", "经营单元ID，关联 dw_dim_org", "id", ("经营单元",)),
            ColumnSpec("industry_id", "INT", "行业ID，关联 dw_dim_industry", "id", ("行业",)),
            ColumnSpec("risk_level", "VARCHAR", "风险等级：高/中/低", "dimension", ("风险等级", "风险")),
            ColumnSpec("risk_type", "VARCHAR", "风险类型：交付延迟/回款逾期/合同变更/客户流失/竞争丢单", "dimension", ("风险类型",)),
            ColumnSpec("amount", "DECIMAL", "风险金额（万元）", "measure", ("风险金额", "金额")),
            ColumnSpec("status", "VARCHAR", "处理状态：跟进中/已升级/已关闭", "dimension", ("状态",)),
            ColumnSpec("created_date", "DATE", "创建日期", "date", ("创建日期",)),
        ),
    ),
)


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "收入额",
        ("收入", "收入额", "销售额", "营收", "销售收入", "收入规模"),
        "各经营单元/行业/产品线实现的收入合计",
        "SUM(dw_fact_revenue.revenue)",
        "万元",
        "amount",
        (("dw_fact_revenue", "revenue"),),
    ),
    MetricSpec(
        "合同额",
        ("合同额", "合同金额", "签约额", "签约金额"),
        "签订合同的金额合计",
        "SUM(dw_fact_revenue.contract_amount)",
        "万元",
        "amount",
        (("dw_fact_revenue", "contract_amount"),),
    ),
    MetricSpec(
        "回款额",
        ("回款", "回款额", "收款", "到账金额"),
        "实际回款的金额合计",
        "SUM(dw_fact_revenue.collection_amount)",
        "万元",
        "amount",
        (("dw_fact_revenue", "collection_amount"),),
    ),
    MetricSpec(
        "业务目标",
        ("商业目标", "目标", "业绩目标", "年度目标"),
        "经营单元承担的商业目标口径（不含税签约额）",
        "SUM(dw_fact_target.biz_target)",
        "万元",
        "amount",
        (("dw_fact_target", "biz_target"),),
    ),
    MetricSpec(
        "商解目标",
        ("商解目标", "解决方案目标"),
        "商业解决方案口径的目标（不含税收入）",
        "SUM(dw_fact_target.sol_target)",
        "万元",
        "amount",
        (("dw_fact_target", "sol_target"),),
    ),
    MetricSpec(
        "完成率",
        ("完成率", "达成率", "目标完成率", "目标达成率"),
        "收入额 ÷ 商业目标 × 100%",
        "SUM(dw_fact_revenue.revenue) / SUM(dw_fact_target.biz_target) * 100",
        "%",
        "ratio",
        (("dw_fact_revenue", "revenue"), ("dw_fact_target", "biz_target")),
    ),
    MetricSpec(
        "回款率",
        ("回款率", "回款比例", "回款完成率"),
        "回款额 ÷ 收入额 × 100%",
        "SUM(dw_fact_revenue.collection_amount) / SUM(dw_fact_revenue.revenue) * 100",
        "%",
        "ratio",
        (("dw_fact_revenue", "collection_amount"), ("dw_fact_revenue", "revenue")),
    ),
    MetricSpec(
        "订单数",
        ("订单数", "订单量", "订单个数", "成交订单数"),
        "订单数量合计",
        "SUM(dw_fact_revenue.order_count)",
        "个",
        "count",
        (("dw_fact_revenue", "order_count"),),
    ),
    MetricSpec(
        "同比增幅",
        ("同比", "同比增幅", "同比变化", "同比增长", "同比增速"),
        "本期与上年同期的变化比例",
        "(本期收入 - 上年同期收入) / 上年同期收入 * 100",
        "%",
        "trend",
        (("dw_fact_revenue", "revenue"),),
    ),
    MetricSpec(
        "高风险项目数",
        ("高风险项目", "高风险项目数", "风险项目数", "风险项目", "项目风险"),
        "风险等级为「高」的项目数量",
        "COUNT(*) WHERE risk_level = '高'",
        "个",
        "count",
        (("dw_fact_project_risk", "risk_level"),),
    ),
)


# 便于检索阶段直接拿到「表 -> 字段」结构
TABLES_BY_NAME: dict[str, TableSpec] = {t.table_name: t for t in TABLE_SPECS}
