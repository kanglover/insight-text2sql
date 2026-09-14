"""问数日志服务：把每次问数的过程指标落库，支撑「日志」页。"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.biz import ChatSession, QueryLog


class LogService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def add_log(
        self, *, session_id: int, payload: dict[str, Any], duration_ms: int
    ) -> int:
        error = payload.get("error") or ""
        status = "失败" if error else "成功"
        async with self.session_factory() as session:
            row = QueryLog(
                session_id=session_id,
                question=payload.get("question", "")[:500],
                sql=payload.get("sql", ""),
                provider=payload.get("provider", ""),
                status=status,
                duration_ms=duration_ms,
                total_tokens=int(payload.get("token_usage") or 0),
                row_count=int(payload.get("row_count") or 0),
                tables_used=json.dumps(payload.get("selected_tables") or [], ensure_ascii=False),
                error=error[:1000],
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def list_logs(
        self,
        *,
        days: int = 30,
        keyword: str = "",
        user_name: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            stmt = select(QueryLog, ChatSession.user_name, ChatSession.title).join(
                ChatSession, ChatSession.id == QueryLog.session_id, isouter=True
            )
            if days > 0:
                stmt = stmt.where(QueryLog.created_at >= datetime.now() - timedelta(days=days))
            if keyword:
                stmt = stmt.where(QueryLog.question.like(f"%{keyword}%"))
            if user_name:
                stmt = stmt.where(ChatSession.user_name == user_name)
            stmt = stmt.order_by(QueryLog.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).all()
            return [
                {
                    "id": log.id,
                    "session_id": log.session_id,
                    "session_title": title or "",
                    "user_name": user or "",
                    "question": log.question,
                    "sql": log.sql,
                    "provider": log.provider,
                    "status": log.status,
                    "duration_ms": log.duration_ms,
                    "total_tokens": log.total_tokens,
                    "row_count": log.row_count,
                    "tables_used": _loads(log.tables_used),
                    "error": log.error,
                    "created_at": log.created_at.isoformat(sep=" ", timespec="seconds")
                    if log.created_at
                    else "",
                }
                for log, user, title in rows
            ]

    async def summary(self, days: int = 30) -> dict[str, Any]:
        since = datetime.now() - timedelta(days=days)
        async with self.session_factory() as session:
            total = (
                await session.execute(
                    select(func.count(QueryLog.id)).where(QueryLog.created_at >= since)
                )
            ).scalar_one()
            failed = (
                await session.execute(
                    select(func.count(QueryLog.id)).where(
                        QueryLog.created_at >= since, QueryLog.status == "失败"
                    )
                )
            ).scalar_one()
            avg_duration = (
                await session.execute(
                    select(func.avg(QueryLog.duration_ms)).where(QueryLog.created_at >= since)
                )
            ).scalar_one()
            avg_tokens = (
                await session.execute(
                    select(func.avg(QueryLog.total_tokens)).where(QueryLog.created_at >= since)
                )
            ).scalar_one()
        return {
            "total": int(total or 0),
            "failed": int(failed or 0),
            "success_rate": round((1 - (failed or 0) / total) * 100, 1) if total else 100.0,
            "avg_duration_ms": int(avg_duration or 0),
            "avg_tokens": int(avg_tokens or 0),
        }

    async def hot_questions(self, *, days: int = 30, threshold: int = 3, limit: int = 8) -> list[str]:
        """按提问频次统计「常问」，对应 demo 应用配置里的「常问设置」。"""
        since = datetime.now() - timedelta(days=days)
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(QueryLog.question, func.count(QueryLog.id).label("cnt"))
                    .where(QueryLog.created_at >= since, QueryLog.status == "成功")
                    .group_by(QueryLog.question)
                    .having(func.count(QueryLog.id) >= threshold)
                    .order_by(func.count(QueryLog.id).desc())
                    .limit(limit)
                )
            ).all()
        return [row[0] for row in rows]


def _loads(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []
