"""会话与消息服务。"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.biz import ChatMessage, ChatSession


class SessionService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def list_sessions(self, days: int = 30, keyword: str = "") -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(ChatSession)
            if days > 0:
                stmt = stmt.where(ChatSession.created_at >= datetime.now() - timedelta(days=days))
            if keyword:
                stmt = stmt.where(ChatSession.title.like(f"%{keyword}%"))
            # 置顶优先，其次按创建时间倒序
            stmt = stmt.order_by(ChatSession.pinned.desc(), ChatSession.created_at.desc())
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_dict(row) for row in rows]

    async def get(self, session_id: int) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = await session.get(ChatSession, session_id)
            if row is None:
                return None
            messages = (
                await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.id.asc())
                )
            ).scalars().all()
            data = self._to_dict(row)
            data["messages"] = [self._message_to_dict(m) for m in messages]
            return data

    async def create(self, title: str = "新对话", user_name: str = "管理员") -> dict[str, Any]:
        async with self.session_factory() as session:
            row = ChatSession(title=title, user_name=user_name)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def ensure_session(
        self, session_id: int | None, question: str, user_name: str
    ) -> dict[str, Any]:
        """有会话就复用；没有就按问题前 20 字建一个（对应 demo 的「新对话自动命名」）。"""
        if session_id:
            existing = await self.get(session_id)
            if existing:
                return existing
        title = question[:20] + ("..." if len(question) > 20 else "")
        return await self.create(title=title, user_name=user_name)

    async def rename(self, session_id: int, title: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ChatSession, session_id)
            if row is None:
                return False
            row.title = title or row.title
            await session.commit()
            return True

    async def toggle_pin(self, session_id: int) -> bool | None:
        async with self.session_factory() as session:
            row = await session.get(ChatSession, session_id)
            if row is None:
                return None
            row.pinned = 0 if row.pinned else 1
            await session.commit()
            return bool(row.pinned)

    async def delete(self, session_id: int) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ChatSession, session_id)
            if row is None:
                return False
            await session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
            await session.delete(row)
            await session.commit()
            return True

    async def clear_messages(self, session_id: int) -> bool:
        async with self.session_factory() as session:
            row = await session.get(ChatSession, session_id)
            if row is None:
                return False
            await session.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
            row.msg_count = 0
            await session.commit()
            return True

    async def append_message(
        self,
        session_id: int,
        role: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        async with self.session_factory() as session:
            session.add(
                ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
                )
            )
            # 注意：这里的 COUNT 会触发 autoflush，刚 add 的消息已经被计入，
            # 因此不能再 +1，否则每条消息都会把计数多算一次。
            count = (
                await session.execute(
                    select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
                )
            ).scalar_one()
            row = await session.get(ChatSession, session_id)
            if row is not None:
                row.msg_count = count
            await session.commit()

    async def set_feedback(self, session_id: int, user_feedback: str = "", admin_feedback: str = "") -> None:
        async with self.session_factory() as session:
            row = await session.get(ChatSession, session_id)
            if row is None:
                return
            if user_feedback:
                row.user_feedback = user_feedback
            if admin_feedback:
                row.admin_feedback = admin_feedback
            await session.commit()

    @staticmethod
    def _to_dict(row: ChatSession) -> dict[str, Any]:
        return {
            "id": row.id,
            "title": row.title,
            "user_name": row.user_name,
            "pinned": bool(row.pinned),
            "msg_count": row.msg_count,
            "user_feedback": row.user_feedback,
            "admin_feedback": row.admin_feedback,
            "created_at": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else "",
            "updated_at": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else "",
        }

    @staticmethod
    def _message_to_dict(row: ChatMessage) -> dict[str, Any]:
        try:
            payload = json.loads(row.payload or "{}")
        except ValueError:
            payload = {}
        return {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "payload": payload,
            "created_at": row.created_at.isoformat(sep=" ", timespec="seconds")
            if row.created_at
            else "",
        }
