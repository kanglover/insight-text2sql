"""反馈服务：用户标注「AI 回复数据有误」→ 管理员在「回复校对」处理。

对应 demo 的 `_qaFeedbacks` 与 `renderFeedbacks`。
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.biz import Feedback


class FeedbackService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def create(
        self,
        *,
        session_id: int,
        question: str,
        user_name: str = "管理员",
        message: str = "",
        ai_reply: str = "",
    ) -> dict[str, Any]:
        async with self.session_factory() as session:
            row = Feedback(
                session_id=session_id,
                question=question[:500],
                user_name=user_name,
                message=message,
                ai_reply=ai_reply,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def list(
        self,
        *,
        status: str = "all",
        keyword: str = "",
        user_keyword: str = "",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        async with self.session_factory() as session:
            conditions = []
            if status != "all":
                conditions.append(Feedback.status == status)
            if keyword:
                conditions.append(Feedback.question.like(f"%{keyword}%"))
            if user_keyword:
                conditions.append(Feedback.user_name.like(f"%{user_keyword}%"))

            count_stmt = select(func.count(Feedback.id))
            list_stmt = select(Feedback)
            for condition in conditions:
                count_stmt = count_stmt.where(condition)
                list_stmt = list_stmt.where(condition)

            total = (await session.execute(count_stmt)).scalar_one()
            rows = (
                (
                    await session.execute(
                        list_stmt.order_by(Feedback.created_at.desc())
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                )
                .scalars()
                .all()
            )
        return {
            "items": [self._to_dict(row) for row in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    async def update(self, feedback_id: int, *, status: str = "", remark: str = "") -> dict[str, Any] | None:
        async with self.session_factory() as session:
            row = await session.get(Feedback, feedback_id)
            if row is None:
                return None
            if status:
                row.status = status
            if remark:
                row.remark = remark
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def stats(self) -> dict[str, int]:
        async with self.session_factory() as session:
            total = (await session.execute(select(func.count(Feedback.id)))).scalar_one()
            pending = (
                await session.execute(
                    select(func.count(Feedback.id)).where(Feedback.status == "待处理")
                )
            ).scalar_one()
            week_ago = datetime.now() - timedelta(days=7)
            recent = (
                await session.execute(
                    select(func.count(Feedback.id)).where(Feedback.created_at >= week_ago)
                )
            ).scalar_one()
        return {"total": int(total or 0), "pending": int(pending or 0), "recent": int(recent or 0)}

    @staticmethod
    def _to_dict(row: Feedback) -> dict[str, Any]:
        return {
            "id": row.id,
            "session_id": row.session_id,
            "question": row.question,
            "user_name": row.user_name,
            "message": row.message,
            "ai_reply": row.ai_reply,
            "status": row.status,
            "remark": row.remark,
            "created_at": row.created_at.isoformat(sep=" ", timespec="seconds")
            if row.created_at
            else "",
            "updated_at": row.updated_at.isoformat(sep=" ", timespec="seconds")
            if row.updated_at
            else "",
        }
