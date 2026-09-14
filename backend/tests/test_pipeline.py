"""流水线端到端测试。

覆盖三条路径：
1. 规则引擎（离线，完全确定）；
2. 大模型（用脚本化的假模型，验证 Prompt 组装、事件顺序、Token 统计）；
3. 校验失败 → 自动修正（先用假模型返回坏 SQL，再返回好 SQL）。
"""

import pytest

from app.repositories.dw_repository import DwRepository
from app.repositories.meta_repository import MetaRepository
from app.text2sql.graph import build_pipeline
from app.text2sql.llm import NullLLM
from app.text2sql.prompts import ANSWER_SYSTEM_PROMPT, SQL_SYSTEM_PROMPT
from app.text2sql.state import PipelineContext
from tests.fakes import ScriptedLLM

GOOD_SQL = (
    'SELECT o.org_name AS "经营单元", SUM(r.revenue) AS "收入额"\n'
    "FROM dw_fact_revenue r JOIN dw_dim_org o ON r.org_id = o.org_id\n"
    "WHERE r.year = 2026 GROUP BY o.org_name ORDER BY \"收入额\" DESC"
)


async def _run(database, snapshot, llm, question, provider="auto"):
    async with database.session() as session:
        context = PipelineContext(
            meta_repository=MetaRepository(session),
            dw_repository=DwRepository(session),
            llm=llm,
            snapshot=snapshot,
            provider=provider,
            max_correction_retry=1,
        )
        state = {
            "query": question,
            "token_usage": 0,
            "warnings": [],
            "correction_attempts": 0,
            "error": None,
        }
        events = [event async for event in build_pipeline().run(state, context)]
    return events, state


@pytest.mark.asyncio
async def test_pipeline_with_rule_engine(database, snapshot):
    events, state = await _run(
        database, snapshot, NullLLM(), "2026年各经营单元的收入和完成率", provider="rule"
    )
    kinds = [e["type"] for e in events]
    assert "progress" in kinds
    assert "sql" in kinds
    assert "result" in kinds
    assert "chart" in kinds
    assert "answer" in kinds
    assert "trace" in kinds

    assert state["error"] is None
    assert state["provider"] == "rule"
    assert state["result"].row_count == 21
    assert "完成率" in state["result"].columns
    assert state["answer"]
    assert state["chart"]["type"] in {"bar", "line"}
    assert state["stats"]["row_count"] == 21

    progress_steps = [e["step"] for e in events if e["type"] == "progress"]
    # 三步特征：先召回、再生成、最后执行
    assert any("召回" in s for s in progress_steps)
    assert any("生成 SQL" in s for s in progress_steps)
    assert any("执行取数" in s for s in progress_steps)


@pytest.mark.asyncio
async def test_pipeline_with_llm_provider(database, snapshot):
    llm = ScriptedLLM([GOOD_SQL, "新疆代表处收入最低，需要重点关注。", "同比趋势如何？\n回款率呢？"])
    events, state = await _run(database, snapshot, llm, "各经营单元收入排名")

    assert state["provider"] == "llm"
    assert state["error"] is None
    assert state["result"].row_count == 21
    assert state["answer"] == "新疆代表处收入最低，需要重点关注。"
    assert state["token_usage"] > 0

    # Prompt 里必须带上关键约束与上下文
    sql_prompt = llm.sql_prompts[0]
    assert "dw_fact_revenue" in sql_prompt
    assert "可用连接路径" in sql_prompt
    assert "只输出一条 SELECT" in SQL_SYSTEM_PROMPT
    assert any(c["system"] == ANSWER_SYSTEM_PROMPT for c in llm.calls)


@pytest.mark.asyncio
async def test_pipeline_auto_falls_back_to_rules_when_llm_unavailable(database, snapshot):
    llm = ScriptedLLM([], available=False)
    _, state = await _run(database, snapshot, llm, "2026年各行业的收入是多少")

    assert state["provider"] == "rule"
    assert state["error"] is None
    assert state["result"].row_count == 14


@pytest.mark.asyncio
async def test_pipeline_corrects_invalid_sql(database, snapshot):
    """第一次返回写操作 SQL（会被安全网关拦下），第二次返回合法 SQL。"""
    llm = ScriptedLLM(["DROP TABLE dw_fact_revenue",
                       GOOD_SQL,
                       "已修正结论。", "追问一\n追问二"])
    events, state = await _run(database, snapshot, llm, "各经营单元收入")

    correction_events = [e for e in events if e["type"] == "correction"]
    assert correction_events, "应当触发过 SQL 修正"
    assert state["correction_attempts"] == 1
    assert state["error"] is None
    assert state["result"].row_count == 21


@pytest.mark.asyncio
async def test_pipeline_reports_error_and_keeps_stream_alive(database, snapshot):
    """模型一直返回非法 SQL 时，流水线不能崩，要给出可读的错误结论。"""
    llm = ScriptedLLM(["SELECT * FROM secret_table", "SELECT * FROM secret_table"])
    events, state = await _run(database, snapshot, llm, "各经营单元收入")

    assert state["error"]
    kinds = [e["type"] for e in events]
    assert "trace" in kinds  # 流水线仍然走到了终点
    assert state["answer"]


@pytest.mark.asyncio
async def test_pipeline_selects_tight_table_set(database, snapshot):
    _, state = await _run(database, snapshot, NullLLM(), "2026年各行业的收入排名", provider="rule")
    tables = state["selected_tables"]
    assert "dw_fact_revenue" in tables
    assert "dw_dim_industry" in tables
    # 与问题无关的事实/维表不应进入上下文
    assert "dw_fact_project_risk" not in tables
