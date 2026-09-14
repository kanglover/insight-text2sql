# 经管问数（Insight Text2SQL）设计说明

> 目标：把 `demo.html` 中「经管之星 · 智能问数」的交互与功能完整落地成一个前后端分离、可部署、有单测的
> Text2SQL 工程。前端 React，后端 Python，数据自己制作。

## 1. 问题拆解

在动手前先把「看起来是一件事」的需求拆成四类独立问题：

| 类别 | 问题 | 结论 |
| --- | --- | --- |
| 交互还原 | demo 里有哪些页面/交互必须实现？ | 侧边栏可达的 4 个页面 + 对话内的 8 类消息态（见 §3） |
| 核心能力 | 「智能问数」本质是什么？ | 自然语言 → 检索元数据 → 生成 SQL → 安全校验 → 执行 → 解读，全链路可解释、可流式 |
| 数据 | demo 的 mock 数据没有真实结构 | 自制销售经管数仓 + 元数据知识库（表/字段/指标/取值/问答样例） |
| 工程 | 验收要求「演示 + review + 单测 + 可部署」 | 分层架构、SSE 流式、SQL 安全网关、pytest 单测、Docker Compose 一键起 |

**关键的三个取舍（为什么这么做）**

1. **不引入向量库 / 搜索引擎 / 独立 Embedding 服务。**
   参考项目 `ec_bot` 用 Qdrant + ES + TEI 三件套，检索能力强但部署成本高（光 Embedding 模型 1.3GB，
   需要 5 个容器）。本项目面向「可部署 + 可单测」，改为**在元数据库上做混合检索**（`jieba` 分词 +
   BM25 风格打分 + 同义词/别名扩展 + 取值字典精确匹配）。接口层抽象成 `Retriever`，
   日后要换向量召回只需新增实现，不改流水线。
2. **自研轻量流水线，不用 LangGraph。**
   `ec_bot` 用 LangGraph。本项目节点只有十几个、分支只有「校验失败则修正」一处，
   为此引入整套图框架会让单测变重（需要跑 graph runtime）。改为**约 90 行的声明式节点编排器**
   （`text2sql/pipeline.py`：节点 + 边 + 条件边），每个节点是纯 async 函数，可单独测、可单独跑。
3. **LLM 走 OpenAI 兼容协议，并且必须有离线兜底。**
   没有 Key / 网络不通时，不能让「演示」和「单测」直接挂。因此实现两套 SQL 生成器：
   `LLMGenerator`（真实大模型）与 `RuleGenerator`（意图模板引擎，覆盖问数场景常见问法）。
   `LLM_PROVIDER=auto` 时优先大模型、失败降级到规则引擎，并在过程里如实标注用了哪条路径。

## 2. 架构

```
浏览器 (React + TS + Vite)
   │  fetch + ReadableStream 解析 SSE
   ▼
FastAPI (backend/)
   ├── api/routers/        chat / sessions / feedback / config / models / logs / health
   ├── services/           业务编排（会话、反馈、配置、日志）
   ├── text2sql/           ★ 核心：流水线
   │     ├── state.py          状态定义
   │     ├── context.py        运行时依赖注入（仓储、LLM、检索器）
   │     ├── pipeline.py       声明式编排器（节点/边/条件边 + 事件流）
   │     ├── graph.py          本项目的流水线定义（节点与连边）
   │     ├── nodes/            11 个节点，一节点一文件
   │     ├── retrieval/        三类召回 + 合并 + 过滤
   │     ├── generators/       LLM 生成器 / 规则生成器
   │     └── sql_guard.py      SQL 安全网关（sqlglot）
   ├── repositories/       MetaRepository（元数据） / DwRepository（数仓）
   ├── models/             SQLAlchemy ORM
   └── db/                 engine / session / init
```

### 流水线（`text2sql/graph.py`）

```
START
  → extract_keywords                抽取关键词（jieba + 词性过滤 + 原始问题兜底）
  → recall_column / recall_metric / recall_value   （三路并行）
  → merge_context                   合并召回，去重、按分数截断
  → filter_tables                   收敛到「真正要用的表」+ 补全字段样例值
  → build_sql_context               补日期、方言、指标口径、few-shot 样例
  → generate_sql                    LLM / 规则引擎生成 SQL
  → validate_sql                    sqlglot 解析 + 安全网关
       ├─ 通过 → execute_sql
       └─ 失败 → correct_sql → execute_sql
  → execute_sql                     只读执行 + 行数上限 + 超时
  → interpret_result                自然语言结论 + 数据统计 + 延伸问题
  → END
```

每个节点都会向事件流写入 `progress`（running/success/error），最终产出 `sql`、`result`、`answer`、
`chart`、`stats`，由 `chat` 接口以 SSE 原样转发给前端 —— 这就是 demo 里「分析过程 ▸」那一段。

## 3. 需求 → 实现映射（验收清单）

| demo 功能 | 实现位置 |
| --- | --- |
| 欢迎页：开场白文案 + 快捷问题宫格，可在应用配置里开关/编辑 | `frontend/pages/AiQa.tsx` + `config` 接口 |
| 会话侧栏：近 30 天记录、开启新对话、置顶/重命名/删除 | `sessions` 接口 |
| 快捷提问面板：常问 / 收藏 两个 Tab | `sessions.quick_questions` + 前端 `QuickPanel` |
| 用户消息：收藏 / 编辑重发 / 重新生成 / 复制 | `frontend/components/UserMessage.tsx` |
| AI 回复：分析过程（可展开步骤）→ 数据发现 → 数据表格 → 数据统计 → 数据可视化 → 耗时/Token → 延伸问题 | `components/AiMessage.tsx` + SSE 事件的 `progress/result/stats/chart/answer` |
| AI 回答「反馈数据有误」 | `feedback` 接口（新增） |
| 日志：过去 7/30/90 天、按用户筛选、搜索 | `logs` 接口 + `pages/Logs.tsx` |
| 系统管理 → 应用配置：6 个开关 + 开场白配置 + 常问设置 | `pages/AppConfig.tsx` + `config` 接口 |
| 系统管理 → 模型配置：选模型、保存、新增模型（含连接测试） | `pages/ModelConfig.tsx` + `models` 接口 |
| 反馈管理 → 回复校对：列表、搜索、状态筛选、分页、处理 | `pages/Feedback.tsx` + `feedback` 接口 |

**明确不做**（题目已说明）：登录、用户管理、权限体系。当前用户以固定上下文（`X-User-Name` 头可选）表示。

## 4. 数据（自制）

数仓（`dw_` 前缀，SQLite/MySQL 通用 DDL 见 `app/data/schema.sql`）：

- 维度：`dw_dim_org`（经营单元，含大区/层级）、`dw_dim_industry`（行业）、`dw_dim_product_line`（产品线）、
  `dw_dim_product`（产品型号）、`dw_dim_date`
- 事实：`dw_fact_revenue`（收入/合同额/回款/订单数，粒度 日期×经营单元×行业×产品）、
  `dw_fact_target`（商业目标/商解目标，粒度 年×经营单元×产品线）、`dw_fact_project_risk`（项目风险）

元数据知识库（`meta_` 前缀）：`meta_table`、`meta_column`、`meta_metric`、`meta_column_metric`、
`meta_value`（字段取值样例）、`meta_question_sql`（自然语言↔SQL 样例，用于 few-shot 与规则引擎/评测）。

数据由 `backend/scripts/seed.py` 以固定随机种子生成，保证可复现。

## 5. 质量与安全

- **SQL 安全网关**（`sql_guard.py`）：只允许单条 `SELECT`；拒绝 DDL/DML/多语句/注释注入；表名白名单；
  强制追加 `LIMIT`；禁止 `SELECT *` 泄漏敏感列（预留）。所有查询走只读连接。
- **单测**：`backend/tests/` 覆盖 SQL 网关、三类召回、规则生成器、流水线端到端（内存 SQLite + Mock LLM）、
  REST 接口（httpx ASGITransport）。前端 `vitest` 覆盖 SSE 解析与图表规格推导。
- **可观测**：请求级 `request_id`（ContextVar）+ 结构化日志；每次问数落库（耗时、Token、命中表、SQL），
  即 demo 里的「日志」。

## 6. 部署

- 本地：`make dev`（后端 uvicorn + 前端 vite，前端代理 `/api`）。
- 容器：`docker compose up -d`（backend + frontend/nginx），数据卷持久化 SQLite；设 `DATABASE_URL` 即切 MySQL。
- 配置全部走环境变量（`backend/.env`，见 `.env.example`）。
