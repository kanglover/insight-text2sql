# 经管之星 · 智能问数（Insight Text2SQL）

把「自然语言问经营数据」做成一个能跑起来的产品：输入一句中文问题，系统自动检索元数据 → 生成 SQL → 安全校验 → 执行取数 → 出表格 / 统计 / 图表 / 结论，全过程流式展示。

> 功能对齐 `demo.html`（销售经管平台「经管之星」），但**代码与数据完全自研**：
> 没有复用任何既有仓库的代码，数仓与元数据知识库是为了这个项目现造的。

前后端分离，分别放在 `backend/` 与 `frontend/`。

---

## 1. 功能清单

| 模块 | 对应 demo 的能力 | 实现情况 |
| --- | --- | --- |
| 智能问数 | 开场白 + 推荐问题 | ✅ 首屏欢迎语、推荐问题可配置 |
| | 会话侧栏（近 30 天记录） | ✅ 新建 / 切换 / 置顶 / 重命名 / 删除 |
| | 流式问数 + 分析过程 | ✅ SSE 推送，13 个节点逐步点亮 |
| | AI 回复四段式 | ✅ ① 数据发现 ② 数据表格 ③ 数据统计 ④ 数据可视化 |
| | 结论与延伸问题 | ✅ 大模型生成，失败自动降级到模板 |
| | 耗时 / Token / 生成方式 | ✅ 每次问数都记录 |
| | 消息动作 | ✅ 复制 / 编辑 / 重新生成 / 收藏 / 语音播放 |
| | 语音播报（文字转语音） | ✅ 浏览器原生 `speechSynthesis`，念前先清洗 Markdown / SQL |
| | 语音输入（语音转文字） | ✅ `webkitSpeechRecognition`，边说边出字，权限失败有可读提示 |
| | 快捷提问面板 | ✅ 常问 / 收藏 / 推荐 三个 Tab |
| | 快速提问（常问 / 收藏） | ✅ 按提问频次自动统计，阈值可配 |
| 日志 | 7 / 30 / 90 天、用户筛选、搜索 | ✅ 另加 CSV 导出与明细弹窗 |
| 系统管理 → 应用配置 | 6 个能力开关 + 开场白 + 常问设置 | ✅ 开关全部真实生效（含文字转语音 / 语音转文字），另有「后端真实生效配置」对照区 |
| 系统管理 → 模型配置 | 选择 / 保存 / 新增模型 + 连接测试 | ✅ 连接测试是真实请求，不是假装成功 |
| 反馈管理 → 回复校对 | 列表 / 搜索 / 状态筛选 / 分页 / 处理 | ✅ 含统计卡片与处理备注 |

按需求要求，**未实现登录与用户管理**。

---

## 2. 技术选型

| 层 | 选择 | 理由 |
| --- | --- | --- |
| 后端 | Python 3.11+ / FastAPI | 异步 + 类型化 + 自带 OpenAPI 文档，SSE 天然好写 |
| ORM | SQLAlchemy 2.0（async） | 换库只改 `DATABASE_URL` |
| 数据库 | SQLite（默认） | 零外部依赖，clone 下来就能跑；可切 MySQL / PostgreSQL |
| 流水线 | 自研 ~90 行编排器 | 只有 13 个节点 + 1 个条件分支，引 LangGraph 属于杀鸡用牛刀；自研的可读性和可测性都更好 |
| SQL 解析 | sqlglot | 做白名单校验、方言归一化、自动补 LIMIT |
| 检索 | jieba + IDF 加权打分 | 元数据规模只有几十张表 / 几百个字段，**不需要向量库**；关键词召回可解释、可单测、零外部依赖 |
| 大模型 | OpenAI 兼容协议（httpx 直连） | 不绑 SDK，换模型只改环境变量 |
| 前端 | React 18 + TypeScript + Vite | 需求指定 React；Vite 构建快、配置少 |
| 图表 | ECharts（按需引入） | 图表规格由后端推导，前端只按 type 渲染 |
| 测试 | pytest + pytest-asyncio + httpx / vitest | 后端内存 SQLite，前端纯函数单测，都不依赖网络 |

**为什么不用向量库**：这个项目要解决的是"哪些表和字段跟这个问题相关"，而不是"语义相似度"。
几十张表的元数据用「分词 + 同义词扩展 + IDF 加权」已经能稳定收敛，而且：
召回结果可解释（能说清为什么命中）、可写断言、部署时不用多起一个服务。
如果元数据涨到几千张表，再把 `Retriever` 换成向量召回即可——接口已经抽象好了。

---

## 3. 目录结构

```
insight-text2sql/
├── backend/
│   ├── app/
│   │   ├── api/routers/        # chat / sessions / feedback / config / models / system
│   │   ├── core/               # 配置、日志（含 request_id 贯穿）
│   │   ├── data/               # ★ 自造数据：维度、事实、元数据、样例问答、种子脚本
│   │   ├── db/                 # 引擎与会话（含只读连接还原）
│   │   ├── models/             # meta_*（知识库）/ dw_*（数仓）/ biz_*（业务）
│   │   ├── repositories/       # 元数据仓储、数仓只读仓储
│   │   ├── services/           # 会话、问数、日志、反馈、配置、模型
│   │   └── text2sql/           # ★ 核心：流水线、检索、SQL 网关、生成器、结果解读
│   ├── scripts/                # seed.py（造数）/ ask.py（命令行问数）
│   ├── tests/                  # 116 个用例
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/                # HTTP 客户端 + SSE 客户端 + 接口封装
│       ├── components/         # 外壳、图标、图表、表格、AI 回复面板、通用控件
│       ├── hooks/              # useSpeech.ts（语音播报 / 语音输入）
│       ├── pages/              # 智能问数 / 日志 / 应用配置 / 模型配置 / 回复校对
│       ├── styles/             # 设计令牌 + 全局样式
│       ├── test/               # 测试基建：setup.ts（补齐 jsdom API）+ fixtures.ts
│       ├── utils/              # 格式化 + speech.ts（语音纯函数）
│       ├── speech.d.ts         # Web Speech API 类型补全（TS 未内置识别部分）
│       └── types.ts            # 与后端返回结构一一对应
│   # 测试与源码同级放置：*.test.ts(x) 共 15 个文件 / 268 个用例
├── deploy/                     # 两个 Dockerfile + nginx 配置 + MySQL 初始化 SQL
├── docs/design.md              # 设计文档（问题拆解、流水线、取舍）
├── docker-compose.yml          # 基础编排（SQLite，零依赖演示）
├── docker-compose.mysql.yml    # ★ MySQL 部署覆盖层（叠加在基础之上）
├── Makefile
└── .env.example
```

---

## 4. 快速开始

### 4.1 Docker（推荐，两条命令）

**演示 / 本地跑（SQLite，零外部依赖）**

```bash
cp .env.example .env          # 不填 LLM_API_KEY 也能跑（走规则引擎）
docker compose up -d --build
open http://localhost:8080
```

**部署到服务器（MySQL）**

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build
# 或：make up-mysql
```

覆盖层会额外拉起一个 `mysql:8.0` 容器（utf8mb4），并把后端的 `DATABASE_URL`
切成 MySQL；后端会等 MySQL 健康探针通过再启动，避免启动竞态。
首次启动会自动建表并灌入自制数据集，不需要额外手工步骤。

默认端口 8080，改 `WEB_PORT` 即可。后端接口文档在 `http://localhost:8080/docs`。

> ⚠️ 改了 `.env` 里的 `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`，
> 必须同步改 `DATABASE_URL` —— compose 不支持在默认值里嵌套引用变量，
> 两者不会自动联动。

#### 用外部已有的 MySQL

不想要 compose 里的 MySQL 容器时，删掉覆盖层里的 `mysql` 服务，直接指过去：

```bash
# 1) 用管理员账号建库（中文必须 utf8mb4）
mysql -uroot -p < deploy/mysql/00-init.sql

# 2) 在 .env 里指向它
DATABASE_URL=mysql+aiomysql://insight:你的密码@10.0.0.8:3306/insight?charset=utf8mb4
```

连接串**必须带 `?charset=utf8mb4`**，否则中文会变成问号。

### 4.2 本地开发

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 按需填 LLM_API_KEY
python -m scripts.seed --stats    # 初始化演示数据
uvicorn app.main:app --reload     # http://127.0.0.1:8000

# 前端（另开一个终端）
cd frontend
npm install
npm run dev                    # http://127.0.0.1:5173（已代理 /api）
```

### 4.3 命令行问数（不启动前端也能验证）

```bash
cd backend
python -m scripts.ask "2026年各经营单元的收入和完成率"
python -m scripts.ask "高风险项目有哪些" --provider rule    # 离线规则引擎
```

### 4.4 部署到 MySQL 的注意事项

代码本身是方言无关的（ORM 用标准类型、SQL 由 sqlglot 按目标方言重新生成），
但换到 MySQL 有几件事必须确认：

| 项 | 为什么 | 怎么做 |
| --- | --- | --- |
| **字符集** | 中文与 emoji 需要四字节，MySQL 的 `utf8` 其实是三字节的 `utf8mb3` | 建库用 `utf8mb4`；连接串带 `?charset=utf8mb4` |
| **驱动** | MySQL 8 默认认证插件是 `caching_sha2_password` | 已装 `aiomysql` + `cryptography`，缺后者会连不上 |
| **连接池** | MySQL / 云 RDS / 代理会掐断空闲连接，池里留死连接就报 2006 | 已开 `pool_pre_ping` + `pool_recycle`（默认 1800s） |
| **时区** | `NOW()` 取的是数据库时区，`created_at` 可能差 8 小时 | 容器已设 `--default-time-zone=+08:00` |
| **ONLY_FULL_GROUP_BY** | MySQL 8 默认开启，比 SQLite 严格；`SELECT` 里出现未聚合且不在 `GROUP BY` 的列会报 1055 | 规则引擎模板已保证完整分组；大模型偶尔写错时会走自动修正重试。想放宽可在 MySQL 侧调 `sql_mode` |
| **只读边界** | MySQL 没有连接级只读开关（见第 7 节） | 用 `deploy/mysql/00-init.sql` 里的 GRANT 收敛应用账号权限 |

首次启动会自动建表 + 灌种子数据（元数据表为空时触发）。想确认数据是否真的写进 MySQL：

```bash
# 进容器直接查
docker compose -f docker-compose.yml -f docker-compose.mysql.yml exec mysql \
  mysql -uinsight -pInsight_2026 insight -e "SELECT COUNT(*) FROM dw_fact_revenue"

# 或者看后端启动日志里的「种子数据写入完成」
docker compose -f docker-compose.yml -f docker-compose.mysql.yml logs backend | head -40
```

---

## 5. 配置

所有可变项走环境变量（本地读 `backend/.env`），代码里没有硬编码密钥。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `auto` | `auto` 有 key 用大模型、失败降级；`openai` 只用大模型；`rule` 只用规则引擎（完全离线） |
| `LLM_BASE_URL` | OpenAI | 任意 OpenAI 兼容服务 |
| `LLM_API_KEY` | 空 | 留空则自动降级到规则引擎，功能不中断 |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名 |
| `DATABASE_URL` | SQLite | 可换 `mysql+aiomysql://…` / `postgresql+asyncpg://…`，MySQL 记得带 `?charset=utf8mb4` |
| `DB_POOL_RECYCLE` | `1800` | 连接池回收秒数，须小于 MySQL `wait_timeout` 才能避开 2006 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` | 连接池常驻与可突发连接数（仅非 SQLite 生效） |
| `SQL_ROW_LIMIT` | `500` | 单次取数行数上限 |
| `SQL_TIMEOUT_SECONDS` | `15` | SQL 执行超时 |
| `SQL_MAX_CORRECTION_RETRY` | `1` | 校验失败后自动修正的次数 |
| `RECALL_TOP_K` / `RECALL_MAX_TABLES` | `12` / `6` | 召回条数与进入上下文的最大表数 |
| `CORS_ORIGINS` | `*` | 支持 `*`、`a.com,b.com`、`["a.com"]` 三种写法 |

---

## 6. 核心流程

```
① 解析问题与关键词   jieba 分词 + 去停用词 + 日期/实体识别
② 召回相关字段       列名/注释/同义词 IDF 加权打分
③ 召回业务指标       指标名/别名/公式匹配（如「完成率」→ 收入/目标*100）
④ 召回字段取值       枚举值精确匹配（经营单元、行业、产品线…）
⑤ 合并检索结果       按分数阈值裁剪，避免上下文被无关字段淹没
⑥ 收敛候选数据表     由命中的列反推表；再用外键图补齐必要维表
⑦ 补充日期与库上下文  年份/季度/月份、方言与库版本
⑧ 组装 SQL 生成上下文  表结构 + 指标公式 + 取值样例 + 连接路径
⑨ 生成 SQL          大模型优先；不可用或失败时走规则引擎模板
⑩ 校验 SQL 安全性    sqlglot 白名单校验（见 §7）
⑪ 失败自动修正       把错误回灌给模型重写一次，仍失败则给出可读原因
⑫ 执行取数           只读连接 + 超时 + 行数上限
⑬ 生成结论与图表     图表规格 / 统计摘要 / 自然语言结论 / 延伸问题
```

第 ⑩ 步之后有一个条件分支：校验通过走 ⑫，不通过走 ⑪ 修正后回到 ⑩。
这条链路就是 `backend/app/text2sql/graph.py` 里声明的图，`/api/pipeline` 可以取到结构。

### 关键设计：连接路径由外键图推导

多表 JOIN 最容易出错。这里不靠模型猜，而是从 ORM 的 `ForeignKey` 定义建一张图，
按「事实表 → 维表」的方向生成可用的 JOIN 片段塞进 Prompt。
并且 `expand_with_dimensions` 会保证事实表命中时，它依赖的维表一定被带上——
否则生成出来的 SQL 会因为缺表而跑不通。

---

## 7. 安全设计

模型生成的 SQL 在落库前必须过四道关（`text2sql/sql_guard.py`）：

1. **只能是一条只读查询**：顶层必须是 `SELECT` / `UNION` / CTE，DDL、DML、PRAGMA 一律拒绝；
2. **表名白名单**：只允许访问元数据里登记过的表，`sqlite_master` 等系统表直接拦截；
3. **禁止 `SELECT *`**：必须显式列出字段（既便于映射中文表头，也避免拉回无用列）；
4. **强制 LIMIT**：没写就自动补 `SQL_ROW_LIMIT`，防止全表扫描打满内存。

此外数仓查询在 **SQLite 上**还会打开**连接级只读开关**（`PRAGMA query_only=ON`），
即使静态校验被绕过也写不进数据。

> 踩过的坑：`PRAGMA query_only` 是**连接级**设置，连接归还连接池时如果不还原，
> 后续写操作会报 `attempt to write a readonly database`。
> 现象是「问数能查、落库 500」，且只在「先查后写」的链路上复现。
> 现在统一在 `Database._restore_connection()` 里还原，并有专门的回归测试钉住。

> **MySQL 上没有等价的连接级只读。** MySQL 的 `SET SESSION TRANSACTION READ ONLY`
> 不允许在活动事务中修改（ERROR 1568），而 SQLAlchemy 的 Session 在首条语句就会
> 自动开事务，所以无法在会话中途可靠插入。因此 MySQL 部署时，四道静态校验之外
> 的边界是**库账号最小权限** —— `deploy/mysql/00-init.sql` 里给出了把应用账号
> 对 `dw_*` / `meta_*` 收敛为只读、只对 `biz_*` 开放读写的 GRANT 脚本。

模型密钥不进数据库：模型配置页只保存后四位提示，真正生效的密钥来自环境变量。

---

## 8. 数据说明（自造）

数据在 `backend/app/data/`，由 `scripts/seed.py` 用**固定随机种子**生成，可重复。

- **数仓（星型模型）**：`dw_dim_org`(21 个经营单元) / `dw_dim_industry`(14 个行业) /
  `dw_dim_product_line`(3 条产品线) / `dw_dim_product`(9 个型号) / `dw_dim_date`，
  事实表 `dw_fact_revenue`（收入/合同/回款/订单）、`dw_fact_target`（商业目标/商解目标）、
  `dw_fact_project_risk`（项目风险）。
- **元数据知识库**：`meta_table` / `meta_column` / `meta_metric` / `meta_column_metric` /
  `meta_value` / `meta_question_sql`。这是 Text2SQL 的"知识底座"——
  表注释、字段角色、指标口径（含公式）、枚举值同义词、20 组「问题 ↔ 标准 SQL」样例。
- **口径自洽**：2026 年北京代表处完成率约 **78%**，与 demo 里展示的量级一致，
  并且有单测断言（`test_completion_rate_matches_seed_caliber`）。
  这样图表、结论、日志三处的数字能互相对上，不会出现"看起来对但口径打架"。

时间跨度 2025–2026 两年，2026 年数据只到 9 月（因此同比类问题默认截到 9 月）。

---

## 9. 测试

```bash
make test                                  # 前后端全部
make test-backend                          # cd backend && pytest -q  → 116 passed
make test-frontend                         # cd frontend && npm run test  → 268 passed
cd frontend && npm run typecheck           # strict + noUnusedLocals
```

合计 **384 个用例**（后端 116 + 前端 268）。

### 后端（pytest，内存 SQLite）

| 文件 | 覆盖内容 |
| --- | --- |
| `test_sql_guard.py` | 白名单、CTE、UNION、DDL 拦截、多语句、系统表、`SELECT *`、自动 LIMIT、方言归一 |
| `test_retrieval.py` | 分词、列/指标/取值召回、上下文裁剪阈值、外键图与表收敛 |
| `test_rule_generator.py` | 20 种意图识别 + 槽位抽取 + 生成的 SQL 真能跑 + 口径断言 |
| `test_chart.py` | 折线/柱状/饼图/指标卡的推导、统计摘要、模板结论 |
| `test_pipeline.py` | 规则 / 大模型 / 降级 / 修正重试 / 报错不崩 五条路径 |
| `test_api.py` | 健康检查、SSE 落库、会话 CRUD、快捷提问与收藏、反馈全流程、配置（含语音开关持久化）、模型、日志 |
| `test_db_session.py` | 只读开关不污染后续写操作（回归）、消息计数正确 |
| `test_db_dialect.py` | 方言解析（含驱动后缀剥离）、只读复位语句按方言下发、MySQL 连接池预检与回收 |
| `test_config.py` | `CORS_ORIGINS` 三种写法、`use_llm` 判定、未知环境变量容错 |

### 前端（vitest + jsdom + Testing Library）

`src/test/setup.ts` 负责补齐 jsdom 缺失的浏览器 API（`ResizeObserver`、
`matchMedia`、`Element.scrollTo`、`URL.createObjectURL` 等），并注册 jest-dom 匹配器；
`src/test/fixtures.ts` 提供 `QueryPayload` / `ChartSpec` / `LogItem` / `AppConfig` 等构造器。
配置见 `vite.config.ts` 的 `test` 段（`environment: jsdom`、`restoreMocks`、`unstubGlobals`）。

| 分组 | 文件（用例数） | 覆盖内容 |
| --- | --- | --- |
| 纯函数 | `utils/speech.test.ts` (21) | 播报文本清洗（剥离代码块/表格/强调）、中文音色择优、超长截断、识别错误码转中文 |
| | `utils/format.test.ts` (24) | 数字/金额/耗时格式化、相对时间、截断、复制降级（`navigator.clipboard` 缺失时退 `execCommand`） |
| API 层 | `api/client.test.ts` (15) | 响应解包、`ApiError` 构造、422 `detail` 提取、`qs()` 编码、网络异常 |
| | `api/stream.test.ts` (10) | SSE 分片解析（跨 chunk 断包）、事件分发、心跳/注释忽略、`AbortController` 中止 |
| | `api/endpoints.test.ts` (18) | 各接口 URL 与参数映射、查询串编码 |
| 通用组件 | `components/Icon.test.tsx` (19) | 图标路径渲染、尺寸、未知名称兜底 |
| | `components/Controls.test.tsx` (18) | Toggle 受控切换、SearchBox 回传、Pagination 边界与页码 |
| | `components/Modal.test.tsx` (11) | Esc 关闭、遮罩点击、内部点击不冒泡、`role="dialog"` |
| | `components/DataTable.test.tsx` (12) | 数值右对齐、长文本截断、`Module` / `DotList` 变体 |
| 业务组件 | `components/ChartView.test.tsx` (21) | mock echarts，断言**双 Y 轴**（比率型走右轴）、柱/线/饼配置、空数据占位 |
| | `components/AnswerPanel.test.tsx` (27) | 四模块渲染、分析步骤折叠、SQL 展开、元信息、追问列表 |
| | `components/AppShell.test.tsx` (15) | 菜单高亮、父子层级（`parent-active` 只高亮文字不铺底色）、路由 Outlet |
| Hook | `hooks/useSpeech.test.tsx` (22) | `useTts` / `useAsr` 状态机：能力探测、播报互斥打断、权限拒绝、`start()` 抛错回滚 |
| 页面 | `pages/LogsPage.test.tsx` (18) | 统计卡、分页、详情弹窗、用户下拉联动、带 BOM 的 CSV 导出 |
| | `pages/AppConfigPage.test.tsx` (17) | 开关 patch、开场白/阈值弹窗、加载失败提示与重试 |

前端另有 `npm run typecheck`（strict，`noUnusedLocals`），生产构建产物不入测试范围。

测试的取舍说明：
- **后端全部跑在内存 SQLite 上**：每个用例一个全新的库，天然隔离，且不落盘。
- **前端组件用 Testing Library 走真实渲染 + `user-event`**，不 shallow；echarts 用 `vi.mock` 挡掉
  （断言的是传给 `setOption` 的配置对象，而不是画布像素）。
- **浏览器语音 API 不依赖真实设备**：`useTts` / `useAsr` 通过 `vi.stubGlobal` 注入伪
  `speechSynthesis` / `webkitSpeechRecognition` 覆盖状态机全部分支；真实运行态另由
  `.tools/screenshot-voice.mjs` 做无头冒烟（按钮渲染 → 点击 → 文案切换，零控制台报错）。

---

## 10. 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat/stream` | SSE 流式问数（前端主用） |
| POST | `/api/chat/query` | 同步问数，一次返回完整结果 |
| GET | `/api/sessions` | 会话列表（天数 / 关键词） |
| GET | `/api/sessions/{id}` | 会话详情（含消息与完整载荷） |
| POST | `/api/sessions/{id}/pin` \| `DELETE /api/sessions/{id}` | 置顶 / 删除 |
| GET | `/api/sessions/quick-questions` | 常问 / 收藏 / 推荐 |
| POST | `/api/sessions/favorites?question=` | 收藏 / 取消收藏 |
| GET | `/api/logs` \| `/api/logs/summary` | 问数日志与统计 |
| GET/POST/PUT | `/api/feedback` | 反馈列表 / 提交 / 处理 |
| GET/PATCH | `/api/config/app` | 应用配置读写 |
| GET | `/api/config/runtime` | 后端真实生效的配置 |
| GET/POST | `/api/models`、`/api/models/test` | 模型清单、新增、连接测试 |
| GET | `/api/pipeline` \| `/api/metadata` | 流水线结构 / 数据字典 |

完整交互式文档：启动后端后访问 `/docs`。

---

## 11. 已知限制与后续可做

- **检索是关键词方案**：元数据规模到几千张表时需要换向量召回（`Retriever` 已抽象）。
- **多轮改写较弱**：当前每轮问题独立解析，没有把上文的问题改写成完整问题，
  所以「那上海呢？」这类指代需要用户自己补全。
- **JOIN 深度无限制**：外键图理论上支持多跳，但没有做「超过 N 跳就拒绝」的保护。
- **MySQL 上缺连接级只读**：`PRAGMA query_only` 那层防御只在 SQLite 生效（MySQL 的
  `SET SESSION TRANSACTION` 不允许在活动事务里改，见第 7 节）。MySQL 部署请务必按
  `deploy/mysql/00-init.sql` 给应用账号收权限，否则四道静态校验就是唯一的数据边界。
- **数值列用的是 `Float`**：金额类字段在 MySQL 上会落成 `FLOAT`，量大时会有精度误差。
  对账级场景建议把 `dw_fact_*` 的金额列改成 `Numeric(18, 2)`。
- **语音能力依赖浏览器实现**：播报用原生 `speechSynthesis`、语音输入用 `webkitSpeechRecognition`
  （Chrome / Edge 完整支持，Safari 部分支持，Firefox 的识别默认关闭）。好处是零后端成本、
  无隐私外发；代价是音色与识别质量受浏览器和操作系统限制。若需要跨端一致的音色或更高识别率，
  把 `useTts` / `useAsr` 的实现换成调后端 TTS/ASR 接口即可，调用方组件不用改。
- **语音输入为单次识别**：`continuous = false`，说完自动结束，避免静默时长时间占用麦克风；
  长问题需要分次说，或改为连续模式并在识别结果里做拼接。
- **图表规格是启发式**：按列名与数值分布推断，特殊业务场景可能想要别的图形，
  可把 `build_chart` 换成按指标配置驱动。
