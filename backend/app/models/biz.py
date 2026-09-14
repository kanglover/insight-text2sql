"""业务库 ORM 模型：会话、消息、问数日志、反馈、配置。

注意：题目明确不要求登录与用户管理，因此这里只用一个字符串表示当前用户，
不建用户表、不做鉴权。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatSession(Base):
    """一次问数会话（对应 demo 左侧「近 30 天记录」的一条）。"""

    __tablename__ = "biz_chat_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    user_name: Mapped[str] = mapped_column(String(64), default="管理员", index=True)
    pinned: Mapped[int] = mapped_column(Integer, default=0)
    msg_count: Mapped[int] = mapped_column(Integer, default=0)
    user_feedback: Mapped[str] = mapped_column(String(32), default="")
    admin_feedback: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    """会话内的一条消息。

    `payload` 存 JSON 字符串：用户消息存纯文本；AI 消息存结构化结果
    （sql / rows / columns / stats / chart / steps / followups），
    这样前端刷新后仍能完整还原「分析过程 + 表格 + 图表」。
    """

    __tablename__ = "biz_chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("biz_chat_session.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class QueryLog(Base):
    """一次问数执行日志（对应 demo 的「日志」页）。"""

    __tablename__ = "biz_query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    question: Mapped[str] = mapped_column(String(500), default="")
    sql: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(16), default="")  # llm / rule
    status: Mapped[str] = mapped_column(String(16), default="成功", index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    tables_used: Mapped[str] = mapped_column(Text, default="[]")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Feedback(Base):
    """用户对 AI 回复的「数据有误」反馈，管理员在「回复校对」里处理。"""

    __tablename__ = "biz_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    question: Mapped[str] = mapped_column(String(500), default="")
    user_name: Mapped[str] = mapped_column(String(64), default="管理员", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    ai_reply: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="待处理", index=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AppSetting(Base):
    """应用配置（单行 JSON），对应「系统管理 → 应用配置」。"""

    __tablename__ = "biz_app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ModelSetting(Base):
    """可选模型清单，对应「系统管理 → 模型配置」。"""

    __tablename__ = "biz_model_setting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str] = mapped_column(String(255), default="")
    model_name: Mapped[str] = mapped_column(String(128), default="")
    # 演示用：仅保存后四位，避免明文落库
    api_key_hint: Mapped[str] = mapped_column(String(64), default="")
    selected: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    # 预留：连接测试结果
    reachable: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")


# 便于脚本与测试统一导入
__all__ = [
    "ChatSession",
    "ChatMessage",
    "QueryLog",
    "Feedback",
    "AppSetting",
    "ModelSetting",
]
