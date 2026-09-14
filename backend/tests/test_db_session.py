"""数据库会话生命周期的回归测试。

这里守的是一个很容易被忽略、但一旦踩中就非常难查的坑：
SQLite 的 `PRAGMA query_only` 是**连接级**开关。数仓查询把它置为 ON 之后，
连接会回到连接池被复用；如果归还前不还原，后续写操作就会报
`attempt to write a readonly database`。

现象往往是「问数能查，但把答案落库时 500」，而且只在
「先查后写」的链路上复现。所以用一条端到端用例把它钉住。
"""

import pytest
from sqlalchemy import func, select, text

from app.models.biz import ChatMessage
from app.repositories.dw_repository import DwRepository
from app.services.session_service import SessionService


@pytest.mark.asyncio
async def test_write_session_still_works_after_readonly_query(database):
    """先跑一次「只读」的数仓查询，再用新会话写库，必须成功。"""
    # 1) 只读查询：会把底层连接置为 query_only=ON
    async with database.session() as session:
        repo = DwRepository(session)
        result = await repo.run("SELECT org_name FROM dw_dim_org LIMIT 3")
        assert result.row_count == 3

    # 2) 紧接着用新会话写入。若只读开关没被还原，这一步会抛
    #    OperationalError: attempt to write a readonly database
    service = SessionService(database.session_factory)
    created = await service.create(title="只读之后的写入")
    await service.append_message(created["id"], "user", "各经营单元收入")

    async with database.session() as session:
        count = (
            await session.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id == created["id"]
                )
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_readonly_guard_blocks_writes_inside_query_session(database):
    """反向验证：只读标志确实在生效期间拦住了写操作，而不是形同虚设。"""
    async with database.session() as session:
        repo = DwRepository(session)
        await repo.explain("SELECT org_name FROM dw_dim_org LIMIT 1")
        with pytest.raises(Exception) as exc:
            await session.execute(text("DELETE FROM dw_dim_org"))
        assert "readonly" in str(exc.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_message_count_is_accurate(database):
    """消息计数应该是真实条数，不能因为 autoflush 被多算一次。"""
    service = SessionService(database.session_factory)
    created = await service.create(title="计数")
    session_id = created["id"]

    await service.append_message(session_id, "user", "你好")
    await service.append_message(session_id, "assistant", "你好，有什么可以帮你？")

    detail = await service.get(session_id)
    assert detail is not None
    assert len(detail["messages"]) == 2
    assert detail["msg_count"] == 2, "msg_count 应当等于真实消息条数"
