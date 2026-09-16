# 经管之星 · 智能问数 —— 常用命令
# 依赖：Python 3.11+、Node 18+；Docker 相关目标需要 docker + docker compose。

PY ?= python3
VENV ?= backend/.venv
PIP := $(VENV)/bin/pip
PYBIN := $(CURDIR)/$(VENV)/bin/python
NPM ?= npm
WEB_PORT ?= 8080
UI_BASE ?= http://127.0.0.1:5173
UI_BASE ?= http://127.0.0.1:5173

.PHONY: help setup venv seed backend frontend dev test test-backend build check \
        docker-build up up-mysql up-demo down logs clean reset mysql-shell \
        smoke smoke-setup

help: ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ 本地开发

venv: ## 创建后端虚拟环境并安装依赖
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r backend/requirements.txt
	$(PIP) install pytest pytest-asyncio ruff

setup: venv ## 一次性初始化前后端依赖
	cd frontend && $(NPM) install

seed: ## 重建演示数据库（维度 + 事实 + 元数据 + 样例问答）
	cd backend && $(PYBIN) -m scripts.seed --stats

seed-keep: ## 只补数据，不清空已有库
	cd backend && $(PYBIN) -m scripts.seed --keep

backend: ## 启动后端（http://127.0.0.1:8000，接口文档 /docs）
	cd backend && $(PYBIN) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend: ## 启动前端开发服务器（http://127.0.0.1:5173，已代理 /api）
	cd frontend && $(NPM) run dev

ask: ## 命令行问数：make ask Q="2026年各经营单元的收入和完成率"
	cd backend && $(PYBIN) -m scripts.ask "$(Q)"

# ------------------------------------------------------------------ 前端人工验收（冒烟截图）

smoke: ## 跑前端 UI 冒烟验收（需先 make frontend 起服务；浏览器见 make smoke-setup）
	cd frontend && node tests/e2e/screenshot.mjs $(UI_BASE)
	cd frontend && node tests/e2e/screenshot-chart.mjs $(UI_BASE)
	cd frontend && node tests/e2e/screenshot-voice.mjs $(UI_BASE)
	@echo "截图已保存到 /tmp/insight-shots；任一脚本报错会以非零码退出"

smoke-setup: ## 安装 Playwright 浏览器（make smoke 前置，仅首次/换机需要）
	cd frontend && $(NPM) exec -- playwright install chromium

# ------------------------------------------------------------------ 质量

test: test-backend test-frontend ## 跑全部测试

test-backend: ## 跑后端单测（内存 SQLite，不落盘）
	cd backend && $(PYBIN) -m pytest -q

test-frontend: ## 跑前端单测（vitest）
	cd frontend && $(NPM) run test

test-verbose: ## 跑后端单测并输出每个用例
	cd backend && $(PYBIN) -m pytest -v

lint: ## 代码风格检查（ruff）
	cd backend && $(PYBIN) -m ruff check .

typecheck: ## 前端类型检查
	cd frontend && $(NPM) run typecheck

check: test-backend typecheck build ## 提交前自检：单测 + 类型 + 构建

build: ## 构建前端生产包到 frontend/dist
	cd frontend && $(NPM) run build

# ------------------------------------------------------------------ Docker

docker-build: ## 构建前后端镜像
	docker compose build

up: up-demo ## 起服务（SQLite，零依赖演示）

up-demo: ## SQLite 版：起服务（默认 http://localhost:8080）
	docker compose up -d --build
	@echo "前端: http://localhost:$(WEB_PORT)   后端文档: http://localhost:$(WEB_PORT)/docs"

up-mysql: ## ★ MySQL 版（部署用）：叠加 docker-compose.mysql.yml
	docker compose -f docker-compose.yml -f docker-compose.mysql.yml up -d --build
	@echo "前端: http://localhost:$(WEB_PORT)   后端文档: http://localhost:$(WEB_PORT)/docs"
	@echo "查看建表与灌数日志: make logs | head -40"

down: ## 停止并移除容器（保留数据卷）
	docker compose down
	docker compose -f docker-compose.yml -f docker-compose.mysql.yml down 2>/dev/null || true

mysql-shell: ## 进 MySQL 命令行（仅 MySQL 部署时可用）
	docker compose -f docker-compose.yml -f docker-compose.mysql.yml exec mysql \
		mysql -uinsight -p$${MYSQL_PASSWORD:-Insight_2026} insight

logs: ## 跟踪容器日志
	docker compose logs -f --tail=100

logs-mysql: ## 跟踪 MySQL 部署的容器日志
	docker compose -f docker-compose.yml -f docker-compose.mysql.yml logs -f --tail=100

reset: ## 停止容器并删除数据卷（会清空历史会话与日志）
	docker compose down -v
	docker compose -f docker-compose.yml -f docker-compose.mysql.yml down -v 2>/dev/null || true

clean: ## 清理本地缓存产物
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf backend/.pytest_cache backend/.ruff_cache frontend/dist
