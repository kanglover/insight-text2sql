"""数据库引擎与会话管理。

默认 SQLite（零外部依赖，方便演示与单测）；把 DATABASE_URL 换成
`mysql+aiomysql://...` 或 `postgresql+asyncpg://...` 即可平滑迁移。

方言差异集中在本模块和 `DwRepository` 处理，业务代码不感知：
- SQLite：连接级只读用 `PRAGMA query_only`，内存库需 StaticPool 复用连接；
- MySQL / PostgreSQL：只读是「事务属性」而非连接属性，`SET SESSION TRANSACTION READ ONLY`
  只对**后续**事务生效，且不允许在活动事务里改（ERROR 1568）。SQLAlchemy 的 Session
  在首条语句就自动开事务，因此无法可靠地在会话中途插入这条语句 —— 目前连接级只读
  仍只在 SQLite 上生效（见 `DwRepository._ensure_readonly`），MySQL 部署的边界是
  静态 SQL 网关 + 库账号最小权限，README 有对应的 GRANT 建议。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.log import get_logger
from app.db.base import Base

logger = get_logger(__name__)

# 连接级只读开关的「关闭」语句。目前只有 SQLite 真正设置过只读，
# 因此只有它需要复位；MySQL / PG 一旦将来启用会话级只读，在这里补上对应语句即可
# （MySQL: SET SESSION TRANSACTION READ WRITE / PG: SET SESSION CHARACTERISTICS ...）。
READ_ONLY_OFF = {"sqlite": "PRAGMA query_only = OFF"}


def dialect_of(url: str) -> str:
    """从 SQLAlchemy URL 里取方言名，例如 `mysql+aiomysql://...` → `mysql`。"""
    scheme = url.split("://", 1)[0]
    return scheme.split("+", 1)[0].lower()


class Database:
    """一个可独立实例化的数据库封装，便于测试里创建隔离的临时库。"""

    def __init__(self, url: str, echo: bool = False) -> None:
        self.url = url
        self.dialect = dialect_of(url)
        connect_args: dict = {}
        kwargs: dict = {"echo": echo, "future": True}
        is_sqlite = self.dialect == "sqlite"
        if is_sqlite:
            connect_args["check_same_thread"] = False
            if ":memory:" in url:
                # 内存库必须复用同一个连接，否则每个连接看到的是不同的空库
                kwargs["poolclass"] = StaticPool
        else:
            # MySQL / PG 走长连接池。对端（MySQL wait_timeout、云 RDS、中间代理）
            # 会主动掐断空闲连接，池里若留下死连接，下一个请求就会报
            # 2006 "Server has gone away"。预检 + 定期回收是标准解法。
            kwargs["pool_pre_ping"] = True
            kwargs["pool_recycle"] = settings.db_pool_recycle
            kwargs["pool_size"] = settings.db_pool_size
            kwargs["max_overflow"] = settings.db_max_overflow
        self.engine = create_async_engine(url, connect_args=connect_args, **kwargs)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def create_all(self) -> None:
        # 先确保所有模型都被导入，Base.metadata 才是完整的
        from app import models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_all(self) -> None:
        from app import models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
            finally:
                await self._restore_connection(session)

    async def _restore_connection(self, session: AsyncSession) -> None:
        """归还连接前，清掉连接级的「只读开关」。

        数仓查询会把会话设为只读（见 `DwRepository._ensure_readonly`），而连接随后会
        回到连接池被其它会话复用；如果不还原，下一次写业务表就会失败：

        - SQLite：`attempt to write a readonly database`
        - MySQL：`ERROR 1792 (25006): Cannot execute statement in a READ ONLY transaction`

        SQLAlchemy 的 reset-on-return 不会替我们还原这些设置，所以必须显式处理。
        各方言对只读的"作用域"不同，因此这里按方言下发对应的复位语句。

        这里用 rollback 而非 commit 收尾：各 Service 都是显式提交的，
        rollback 不会丢数据，同时也是 `AsyncSession.close()` 本身的行为。
        """
        reset_sql = READ_ONLY_OFF.get(self.dialect)
        if reset_sql:
            try:
                await session.execute(text(reset_sql))
            except Exception:  # pragma: no cover - 兜底清理，失败不应影响主流程
                logger.debug("还原连接只读开关失败，忽略", exc_info=True)
        try:
            await session.rollback()
        except Exception:  # pragma: no cover
            logger.debug("重置会话事务状态失败，忽略", exc_info=True)

    async def dispose(self) -> None:
        await self.engine.dispose()


db = Database(settings.database_url, settings.db_echo)
