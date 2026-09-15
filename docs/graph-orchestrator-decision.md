# 流水线编排：自研实现 vs LangGraph

> 决策记录（ADR 风格）。说明当前 `text2sql/pipeline.py` + `text2sql/graph.py`
> 为何选择自研声明式编排器而非 LangGraph，其收益与不足，以及在什么条件下应当迁移，
> 并给出 LangGraph 版本的单测写法作为对照。

## 0. 背景

`docs/design.md` §1 取舍点 2 已明确「自研轻量流水线，不用 LangGraph」。本文件把该取舍
展开成可落地的收益/不足清单，并补充迁移成本与测试对照，供后续是否换框架做判断。

相关实现：

- `backend/app/text2sql/pipeline.py` —— 编排器（`Node` / `Edge` / `ConditionalEdge` / `run`）
- `backend/app/text2sql/graph.py` —— 本项目 13 节点的图定义 + `_validate_router` 条件分支
- `backend/app/text2sql/nodes/*.py` —— 一节点一文件，纯 async 函数
- `backend/tests/test_pipeline.py` —— 端到端单测（规则引擎 / LLM / 自动修正 / 错误兜底）

## 1. 当前实现长什么样

编排器核心（约 140 行）：

- `Node(name, label, fn)`：`fn` 是纯 async 函数 `async (state, context, emit) -> dict | None`，
  返回值是要合并进 `state` 的字典差分。
- `Edge(source, target)`：无条件跳转。
- `ConditionalEdge(source, router, mapping)`：按 `state` 决定下一个节点。
- `Pipeline.run(state, context)`：带「最多 64 步」防御性上限的 `for` 循环 + `route()` 决定下一节点；
  每个节点前后自动发 `progress` 事件，节点内部可经 `emit()` 发任意业务事件；整体是 `AsyncIterator`，
  `yield` 出的事件被 SSE 原样转发。

`graph.py` 唯一的真实分支在 `validate_sql`：用 `_validate_router` 看 `state["error"]` 与
`correction_attempts` 决定走 `run_sql` 还是 `correct_sql`。

## 2. 自研的好处

1. **单测极轻、确定性极高（最大收益）**
   节点是纯 async 函数，可直接 `await node.fn(state, ctx, emit)` 单测，也可
   `build_pipeline().run(state, context)` 端到端测。配合 `NullLLM` / `ScriptedLLM`（假模型）
   与内存 SQLite，整条链路不碰网络、不依赖 graph runtime，`tests/test_pipeline.py` 中 6 个测试
   全部确定性通过。
2. **依赖少、部署小**
   无 `langgraph` + `langchain-core` + `pydantic` 重型依赖链，`docker compose` 镜像更小、pip 更快，
   少一层版本兼容地雷。
3. **事件流完全可控**
   `emit` 直接产生 `progress / sql / result / chart / answer / trace` 等业务级事件，
   `run()` 作为异步生成器原样 `yield`，SSE 直接转发，无中间序列化/反序列化。
4. **可读、可改、可调试**
   改边即改 `graph.py` 几行，节点函数零改动；代码量小，自带 `mermaid()` 便于文档对照。

## 3. 自研的不足

1. **无内置并行执行**
   三路召回在当前实现里顺序执行（`docs/design.md` 已注明）。召回是纯内存打分、毫秒级，现状无所谓；
   但若将来召回接真实向量库/ES，顺序执行会拖慢首字延迟。并行需自行 `asyncio.gather`。
2. **无持久化 / 断点续跑 / 人机协同**
   `run()` 一旦进入就跑到黑，中途插入「人工确认 SQL」等 human-in-the-loop 需自造状态机；
   LangGraph 的 checkpoint 原生支持 pause/resume。
3. **循环/重试逻辑手写**
   「校验失败→修正，最多 N 次」靠 `_validate_router` 计数 `correction_attempts`；
   分支再增长（多轮澄清、子图）时该简单循环维护成本上升。
4. **状态是裸 dict，无类型约束**
   `state` 字段拼错只会在运行时 `KeyError`；LangGraph 用 `TypedDict`/pydantic state，schema 层拦截。
5. **缺可视化/调试生态**
   当前仅有 `mermaid()`；LangGraph 有 Studio / LangSmith 可视化 trace，排查「哪步拐错」更直观。

## 4. 改用 LangGraph 是否更方便？

- **短期（加节点、改边）：不会更方便，甚至略繁琐。**
  当前加节点 = `graph.py` 加 `Node(...)` + 一条边，节点函数零改动；LangGraph 同样要加节点改边，
  但要用 `StateGraph.add_node/add_edge/add_conditional_edges` API 并先定义 `State` schema。
- **中期（并行、分支变多、human-in-the-loop、断点续跑）：明显更方便。**
  这些能力是 LangGraph 内置的，不必自造轮子。
- **迁移成本点（`docs/design.md` 未说透）：`emit` 与 `context` 需重新接线。**
  LangGraph 节点签名是 `(state) -> dict`，没有 `emit` 也没有 `context`。节点里大量
  `emit({...})`（见 `nodes/sql_nodes.py` 第 61/71/102 行）迁移时须改为往 `state["events"]` 追加
  （`Annotated[list, operator.add]`），并将 `context`（仓库 / LLM / snapshot）塞进 LangGraph 的
  `config` / `store`，节点从 config 取用。这部分是真实工作量，不是「换个 `run` 就行」。

## 5. 用 LangGraph 的话，单测怎么写？

整体思路与现有测试同构：单节点直接调函数，整图用流式 API 收集事件，条件边测 router 函数，假 LLM 照用。

### 5.1 图定义骨架（LangGraph 版 `graph.py`）

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
import operator

class PipelineState(TypedDict, total=False):
    query: str
    sql: str
    error: str | None
    correction_attempts: int
    events: Annotated[list, operator.add]   # 把 emit 改成往这里累积
    # ...其余字段

def _validate_router(state):
    if state.get("error") is None:
        return "run_sql"
    if int(state.get("correction_attempts") or 0) == 0:
        return "correct_sql"
    return "run_sql"

builder = StateGraph(PipelineState)
for n in nodes:
    builder.add_node(n.name, n.fn)          # fn 改成 (state)->dict，内部往 events 追加
builder.add_edge("extract_keywords", "recall_column")
# ... 其余边
builder.add_conditional_edges(
    "validate_sql", _validate_router,
    {"run_sql": "run_sql", "correct_sql": "correct_sql"},
)
builder.add_edge("run_sql", "interpret_result")
builder.add_edge("interpret_result", END)
app = builder.compile()
```

### 5.2 单节点测试（与现有几乎一致）

```python
async def test_generate_sql_node():
    state = {"query": "...", "candidate_tables": [...], "db_info": {...}}
    out = await generate_sql({**state, "events": []})   # LangGraph 签名下
    assert out["sql"].startswith("SELECT")
```

### 5.3 整图端到端（对照 `test_pipeline_corrects_invalid_sql`）

```python
@pytest.mark.asyncio
async def test_pipeline_corrects_invalid_sql(database, snapshot):
    llm = ScriptedLLM(["DROP TABLE dw_fact_revenue", GOOD_SQL, "已修正结论。", "追问一\n追问二"])
    app = build_langgraph_app(llm)  # 把 llm 通过 config/store 注入
    final = {"events": []}
    async for chunk in app.astream(
        {"query": "各经营单元收入"},
        config={"configurable": {"llm": llm}},
        stream_mode="updates",
    ):
        for node, patch in chunk.items():
            if node != "__end__":
                final["events"].extend(patch.get("events", []))
                final.update({k: v for k, v in patch.items() if k != "events"})
    correction = [e for e in final["events"] if e["type"] == "correction"]
    assert correction, "应当触发过 SQL 修正"
    assert final["correction_attempts"] == 1
    assert final["error"] is None
```

### 5.4 关键差异

- LangGraph 的「事件」是 **state 的增量更新**，不是自研的 `progress/sql/result` dict。
  要断言这些业务事件类型，须在节点里把它们写进 `state["events"]`（用 `operator.add` 累积），
  再以 `stream_mode="updates"` 抓取。
- **确定性**：不开 checkpoint 时 LangGraph 纯内存执行，确定性没问题；一旦开 `MemorySaver` 测断点，
  每个测试必须给唯一 `thread_id`，否则测试互相串味。
- 假 LLM、内存 SQLite 这套**完全复用** `tests/fakes.py`，无需重写。

## 6. 结论与迁移触发条件

- **当前规模（13 节点、1 处条件分支、可部署 + 可单测为硬指标）：自研选择正确。**
  现有测试已证明轻量与确定性优势。
- **换 LangGraph 的触发信号**：出现以下需求中的 **≥2 项** ——
  并行召回、多轮澄清、human-in-the-loop、断点续跑。
- 迁移不只是「换 `run`」：需把 `emit` / `context` 重新接线到 LangGraph 的 `state` / `config`。

### 不换框架也能先做的改进

- 把三路召回改成 `asyncio.gather` 并行（不引入任何框架），消除顺序执行的首字延迟。
- 给 `PipelineState` 加一层 `TypedDict` 类型注解，IDE 补全 + 运行前校验，缓解裸 dict 风险。
