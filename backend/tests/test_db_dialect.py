"""数据库方言适配的单测。

这些用例不需要真的连上 MySQL —— 断言的是「不同方言下会下发什么语句」，
把方言差异锁在测试里，避免有人改回只认 SQLite 的写法。

背景：连接归还池前的「只读复位」是典型的跨方言坑。SQLite 的 `PRAGMA query_only`
是连接级开关，必须显式关闭，否则连接被复用后写库直接报
`attempt to write a readonly database`。MySQL 的 `SET SESSION TRANSACTION` 则
不允许在活动事务中修改（ERROR 1568），而 SQLAlchemy 的 Session 在首条语句就会
自动开事务，所以无法在会话中途可靠插入 —— 因此 MySQL 的边界落在静态 SQL 网关
和库账号最小权限上（`deploy/mysql/00-init.sql` 里有 GRANT 建议）。
"""

import pytest

from app.core.config import settings
from app.db.session import READ_ONLY_OFF, Database, dialect_of


class _FakeSession:
    """只记录被执行的语句，不碰真实数据库。"""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.rolled_back = False

    async def execute(self, statement):  # noqa: ANN001 - 只需要可字符串化的语句
        self.statements.append(str(statement))
        return None

    async def rollback(self) -> None:
        self.rolled_back = True


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("sqlite+aiosqlite:///:memory:", "sqlite"),
        ("sqlite+aiosqlite:////data/insight.db", "sqlite"),
        ("mysql+aiomysql://u:p@host:3306/insight?charset=utf8mb4", "mysql"),
        ("mysql+pymysql://u:p@host:3306/insight", "mysql"),
        ("postgresql+asyncpg://u:p@host:5432/insight", "postgresql"),
    ],
)
def test_dialect_of_ignores_driver_suffix(url, expected):
    """方言名要剥掉驱动后缀：`mysql+aiomysql` 与 `mysql+pymysql` 都是 mysql。"""
    assert dialect_of(url) == expected


def test_sqlite_is_the_only_dialect_setting_connection_readonly():
    """目前只有 SQLite 真正置过只读，所以也只有它需要复位语句。

    这条用例的意义在于：将来若给 MySQL / PG 加上会话级只读，必须同步在
    `READ_ONLY_OFF` 里补复位语句，否则连接回池后写不动业务表。
    """
    assert READ_ONLY_OFF == {"sqlite": "PRAGMA query_only = OFF"}


@pytest.mark.asyncio
async def test_restore_connection_resets_readonly_on_sqlite():
    db = Database("sqlite+aiosqlite:///:memory:")
    session = _FakeSession()
    await db._restore_connection(session)
    assert session.statements == ["PRAGMA query_only = OFF"]
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_restore_connection_rolls_back_without_reset_on_mysql():
    """MySQL 没置过连接级只读，就不该多下发语句 —— 但事务状态仍要复位。

    这里只测 mysql：asyncpg 是可选依赖，测试环境没装，构造 PG 引擎会直接
    ModuleNotFoundError。PG 的方言解析由上面的纯字符串用例覆盖。
    """
    db = Database("mysql+aiomysql://u:p@host:3306/insight?charset=utf8mb4")
    session = _FakeSession()
    await db._restore_connection(session)
    assert session.statements == []
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_restore_connection_still_rolls_back_for_unknown_dialect():
    """方言没登记复位语句时，也不能把会话留在脏事务里。"""
    db = Database("sqlite+aiosqlite:///:memory:")
    db.dialect = "oracle"  # 故意用一个表里没有的方言
    session = _FakeSession()
    await db._restore_connection(session)
    assert session.statements == []
    assert session.rolled_back is True


def test_mysql_engine_enables_pool_hardening():
    """MySQL 是长连接池，必须开预检 + 定期回收。

    对端（MySQL 的 wait_timeout、云 RDS、中间代理）会掐断空闲连接，
    池里留下死连接就会报 2006 "Server has gone away"。
    """
    db = Database("mysql+aiomysql://u:p@host:3306/insight?charset=utf8mb4")
    pool = db.engine.pool
    assert type(pool).__name__ != "StaticPool", "MySQL 不应该复用静态连接池"
    assert pool._recycle == settings.db_pool_recycle
    assert pool._pre_ping is True


def test_sqlite_engine_keeps_plain_pooling():
    """SQLite 不该被套上长连接池参数，避免无谓的连接复用开销。"""
    db = Database("sqlite+aiosqlite:////tmp/insight-probe.db")
    assert "_pre_ping" not in vars(db.engine.pool) or db.engine.pool._pre_ping is False


def test_in_memory_sqlite_still_uses_static_pool():
    """内存库必须复用同一条连接，否则每个连接看到的是不同的空库。"""
    db = Database("sqlite+aiosqlite:///:memory:")
    assert type(db.engine.pool).__name__ == "StaticPool"
