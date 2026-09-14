"""图表规格与统计摘要的推导测试（纯函数，不依赖数据库）。"""

from app.text2sql.nodes.interpret import (
    build_chart,
    build_stats,
    format_value,
    template_answer,
)


def test_line_chart_for_time_axis():
    chart = build_chart(
        ["月份", "合同额"], [[1, 100.0], [2, 200.0], [3, 300.0]]
    )
    assert chart["type"] == "line"
    assert chart["x"] == "月份"
    assert chart["series"] == ["合同额"]
    assert chart["data"][0] == {"name": 1, "合同额": 100.0}


def test_bar_chart_for_category_axis():
    chart = build_chart(
        ["经营单元", "收入额"], [["北京代表处", 6210.2], ["上海代表处", 5765.5]]
    )
    assert chart["type"] == "bar"
    assert len(chart["data"]) == 2


def test_pie_chart_for_ratio_column():
    chart = build_chart(
        ["产品线", "占比"], [["通用计算", 55.6], ["智能计算", 35.2], ["商业解决方案", 9.3]]
    )
    assert chart["type"] == "pie"
    assert chart["name"] == "占比"
    assert chart["data"][0] == {"name": "通用计算", "value": 55.6}


def test_metric_card_for_single_row():
    chart = build_chart(["高风险项目数", "风险金额"], [[7, 5640.0]])
    assert chart["type"] == "metric"
    assert {m["label"] for m in chart["metrics"]} == {"高风险项目数", "风险金额"}


def test_multi_series_bar():
    chart = build_chart(
        ["经营单元", "收入额", "商业目标"],
        [["北京代表处", 6210.2, 7950.0], ["上海代表处", 5765.5, 7070.0]],
    )
    assert chart["type"] == "bar"
    assert set(chart["series"]) == {"收入额", "商业目标"}


def test_chart_returns_none_for_empty_result():
    assert build_chart(["经营单元"], []) is None
    assert build_chart([], []) is None


def test_build_stats():
    stats = build_stats(
        ["经营单元", "收入额"], [["A", 100.0], ["B", 300.0], ["C", 200.0]]
    )
    assert stats["row_count"] == 3
    measure = stats["measures"][0]
    assert measure["name"] == "收入额"
    assert measure["sum"] == 600.0
    assert measure["avg"] == 200.0
    assert measure["max"] == 300.0
    assert measure["min"] == 100.0


def test_template_answer_lists_top_rows():
    text = template_answer(
        "各经营单元收入",
        ["经营单元", "收入额"],
        [["北京代表处", 6210.2], ["上海代表处", 5765.5]],
    )
    assert "共查询到 2 条记录" in text
    assert "北京代表处" in text


def test_template_answer_for_empty_result():
    text = template_answer("不存在的经营单元", ["经营单元"], [])
    assert "未查询到" in text


def test_format_value():
    assert format_value(6210.2) == "6,210.2"
    assert format_value(7950) == "7,950"
    assert format_value("北京代表处") == "北京代表处"
