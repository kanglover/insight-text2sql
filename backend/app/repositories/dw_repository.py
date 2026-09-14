"""数仓仓储：只读执行 SQL。

安全策略（纵深防御）：
1. 进入执行前，SQL 必须已经通过 `sql_guard` 的静态校验；
2. 连接层面打开只读开关（目前仅 SQLite 的 `PRAGMA query_only` 支持）；
   MySQL / PostgreSQL 上这一层要改用库账号最小权限，见 `_ensure_readonly` 的说明；
3. 统一包一层超时，避免慢 SQL 拖垮服务；
4. 结果集行数上限由配置控制，避免一次拉回过多数据。
"""

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.log import get_logger
from app.entities import QueryResult

logger = get_logger(__name__)

# 只有这些方言能做「连接级只读」，其它方言靠下面的日志提示运维补上库账号权限
_READONLY_DIALECTS = frozenset({"sqlite"})


class DwRepository:
    def __init__(self, session: AsyncSession, row_limit: int | None = None) -> None:
        self.session = session
        self.row_limit = row_limit or settings.sql_row_limit
        self._readonly_ready = False

    @property
    def dialect(self) -> str:
        return self.session.bind.dialect.name if self.session.bind else "sqlite"

    async def _ensure_readonly(self) -> None:
        """尽力从连接层面禁止写操作，失败/不支持时降级到静态校验。

        注意：MySQL / PostgreSQL 上连接级只读**不生效**。原因是它们的只读是事务属性
        （`SET SESSION TRANSACTION READ ONLY` 只对后续事务生效，且不允许在活动事务里
        修改，ERROR 1568），而 SQLAlchemy 的 Session 在首条语句就自动开事务，
        会话中途无法可靠地插入这条语句。硬塞会把「防护」变成「随机报错」。

        因此在这些方言上，第 2 层防护改由**数据库账号的最小权限**承担（README 给了
        GRANT 语句），这里只提示一次，避免运维误以为双重防护都在。
        """
        if self._readonly_ready:
            return
        dialect = self.dialect
        if dialect in _READONLY_DIALECTS:
            # 双保险：静态校验之外，再从连接层面禁止写操作
            await self.session.execute(text("PRAGMA query_only = ON"))
        else:
            logger.info(
                "当前方言 %s 未启用连接级只读，数仓查询的写入防护依赖 sql_guard 静态校验；"
                "建议为应用账号只授予 dw_* 表的 SELECT 权限（见 README 部署章节）",
                dialect,
            )
        self._readonly_ready = True

    async def get_db_info(self) -> dict[str, str]:
        dialect = self.dialect
        version = "unknown"
        try:
            if dialect == "sqlite":
                row = (await self.session.execute(text("SELECT sqlite_version()"))).first()
            else:
                row = (await self.session.execute(text("SELECT VERSION()"))).first()
            if row:
                version = str(row[0])
        except Exception:  # pragma: no cover - 版本查询失败不影响主流程
            version = "unknown"
        return {"dialect": dialect, "version": version}

    async def explain(self, sql: str) -> None:
        """用 EXPLAIN 让数据库真正解析一次 SQL，解析失败即视为不可执行。"""
        await self._ensure_readonly()
        await self.session.execute(text(f"EXPLAIN {sql}"))

    async def run(self, sql: str) -> QueryResult:
        await self._ensure_readonly()
        try:
            result = await asyncio.wait_for(
                self.session.execute(text(sql)), timeout=settings.sql_timeout_seconds
            )
        except TimeoutError as exc:  # pragma: no cover - 触发需要构造慢查询
            raise TimeoutError(f"SQL 执行超时（>{settings.sql_timeout_seconds}s）") from exc
        rows = result.fetchall()
        columns = list(result.keys())
        data: list[list[Any]] = []
        for i, row in enumerate(rows):
            if i >= self.row_limit:
                break
            data.append([_normalize(v) for v in row])
        return QueryResult(columns=columns, rows=data)


def _normalize(value: Any) -> Any:
    """把 datetime / Decimal 等转成可 JSON 序列化的值。"""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)
