"""pytest 公共夹具。

测试库统一用 **内存 SQLite + StaticPool**：
- 每个测试一个全新的库，天然隔离，不会互相污染；
- 不落盘，既快又不占用磁盘（种子库单库约 8MB，几百个用例用临时文件会直接吃满磁盘）；
- StaticPool 复用同一条连接，`PRAGMA query_only` 这类连接级开关必须在归还时
  还原——这件事已经收敛到 `Database._restore_connection()` 里统一处理，
  所以「只读连接污染写入」的问题不会再出现，也不需要用临时文件来规避。
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.data.seed import seed_database
from app.db.session import Database
from app.entities import MetaSnapshot
from app.repositories.meta_repository import MetaRepository


@pytest_asyncio.fixture
async def database() -> AsyncIterator[Database]:
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_all()
    await seed_database(db, reset=True)
    yield db
    await db.dispose()


@pytest_asyncio.fixture
async def snapshot(database: Database) -> MetaSnapshot:
    async with database.session() as session:
        return await MetaRepository(session).snapshot()


@pytest_asyncio.fixture
async def client(database: Database) -> AsyncIterator[AsyncClient]:
    """把应用的依赖全部指向测试库。

    注意不触发 lifespan（ASGITransport 不发送 lifespan 事件），
    否则应用启动时会去初始化全局的正式库。
    """
    from app.api import deps
    from app.main import app
    from app.services.config_service import ConfigService
    from app.services.feedback_service import FeedbackService
    from app.services.log_service import LogService
    from app.services.model_service import ModelService
    from app.services.query_service import QueryService
    from app.services.session_service import SessionService

    overrides = {
        deps.get_database: lambda: database,
        deps.get_session_service: lambda: SessionService(database.session_factory),
        deps.get_log_service: lambda: LogService(database.session_factory),
        deps.get_feedback_service: lambda: FeedbackService(database.session_factory),
        deps.get_config_service: lambda: ConfigService(database.session_factory),
        deps.get_model_service: lambda: ModelService(database.session_factory),
        deps.get_query_service: lambda: QueryService(database),
    }
    app.dependency_overrides.update(overrides)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
