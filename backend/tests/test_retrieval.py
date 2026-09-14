"""检索层测试：分词、三路召回、表收敛、连接路径。"""

from app.text2sql.retrieval import (
    RetrievalResult,
    merge_context,
    recall_columns,
    recall_metrics,
    recall_values,
)
from app.text2sql.schema_graph import (
    expand_with_dimensions,
    join_map,
    join_paths,
    pick_fact_table,
)
from app.utils.text import query_terms, tokenize


def test_tokenize_drops_stopwords():
    tokens = tokenize("请帮我统计一下各经营单元的收入是多少")
    assert "经营" in tokens or "经营单元" in tokens
    assert "请" not in tokens
    assert "一下" not in tokens


def test_query_terms_keeps_long_ngrams():
    terms = query_terms("2026年各经营单元的收入排名")
    assert "经营单元" in terms
    assert "2026" in terms


def test_recall_values_finds_real_enum(snapshot):
    hits = recall_values("北京代表处今年的达成情况", snapshot)
    values = {(h.value.column_name, h.value.value) for h in hits}
    assert ("org_name", "北京代表处") in values
    # 单字值不应该被误召回
    assert not any(h.value.value == "高" for h in hits)


def test_recall_values_matches_year_synonym(snapshot):
    hits = recall_values("今年各行业的收入", snapshot)
    assert any(h.value.value == "2026" for h in hits)


def test_recall_metrics_hits_completion_rate(snapshot):
    hits = recall_metrics("2026年各经营单元的完成率", ["完成率"], snapshot)
    names = [h.metric.metric_name for h in hits]
    assert "完成率" in names


def test_recall_columns_prefers_measure_over_join_key(snapshot):
    hits = recall_columns("2026年各经营单元的收入", ["收入"], snapshot)
    top = [h.column.qualified_name for h in hits[:6]]
    assert "dw_fact_revenue.revenue" in top
    # 外键字段（org_id）不应该排在度量字段前面
    assert top.index("dw_fact_revenue.revenue") < (
        top.index("dw_fact_revenue.org_id") if "dw_fact_revenue.org_id" in top else 99
    )


def test_merge_context_keeps_needed_tables(snapshot):
    hits = {
        "columns": recall_columns("2026年各经营单元的收入和完成率", [], snapshot),
        "metrics": recall_metrics("2026年各经营单元的收入和完成率", [], snapshot),
        "values": recall_values("2026年各经营单元的收入和完成率", snapshot),
    }
    tables = merge_context(
        RetrievalResult(**hits), snapshot, max_tables=8
    )
    names = [t.table_name for t in tables]
    assert "dw_fact_revenue" in names
    assert "dw_fact_target" in names


def test_schema_graph_join_map_from_foreign_keys():
    mapping = join_map()
    assert ("org_id", "dw_dim_org", "org_id") in mapping["dw_fact_revenue"]
    assert ("product_id", "dw_dim_product", "product_id") in mapping["dw_fact_revenue"]


def test_expand_with_dimensions_only_adds_relevant():
    names = expand_with_dimensions(
        ["dw_fact_revenue"], relevant={"dw_dim_org"}, max_tables=8
    )
    assert "dw_dim_org" in names
    # 与问题无关的维表不应该被塞进上下文
    assert "dw_dim_industry" not in names


def test_pick_fact_table_when_only_dim_selected():
    assert pick_fact_table(["dw_dim_org"]) == "dw_fact_revenue"


def test_join_paths_are_readable():
    paths = join_paths(["dw_fact_revenue", "dw_dim_org"])
    assert "dw_fact_revenue.org_id = dw_dim_org.org_id" in paths
