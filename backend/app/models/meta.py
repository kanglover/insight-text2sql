"""元数据知识库 ORM 模型。

这组表回答的是「数仓里有什么、怎么用」：
- 表 / 字段是什么、有什么业务含义（meta_table / meta_column）
- 业务在说的「指标」对应什么口径、依赖哪些字段（meta_metric / meta_column_metric）
- 字段的真实取值长什么样，用于把「上海代表处」这类词映射到 where 条件（meta_value）
- 常见的自然语言问法对应什么 SQL，用于 few-shot 与离线规则引擎（meta_question_sql）
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetaTable(Base):
    __tablename__ = "meta_table"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    table_comment: Mapped[str] = mapped_column(String(255), default="")
    # fact（事实表）/ dim（维度表），用于给模型提示 join 方向
    table_role: Mapped[str] = mapped_column(String(16), default="fact")
    business_domain: Mapped[str] = mapped_column(String(64), default="")
    # 检索排序用的先验权重：越核心的表越大
    priority: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MetaColumn(Base):
    __tablename__ = "meta_column"
    __table_args__ = (UniqueConstraint("table_name", "column_name", name="uq_meta_column"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), index=True)
    column_name: Mapped[str] = mapped_column(String(128), index=True)
    data_type: Mapped[str] = mapped_column(String(64), default="")
    column_comment: Mapped[str] = mapped_column(String(255), default="")
    # dimension / measure / date / id，决定这个字段能不能聚合、能不能当分组维度
    semantic_role: Mapped[str] = mapped_column(String(16), default="dimension")
    # JSON 数组字符串，例如 '["产品线","产品大类"]'
    synonyms: Mapped[str] = mapped_column(Text, default="[]")
    is_primary: Mapped[int] = mapped_column(Integer, default=0)


class MetaMetric(Base):
    __tablename__ = "meta_metric"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    aliases: Mapped[str] = mapped_column(Text, default="[]")
    description: Mapped[str] = mapped_column(Text, default="")
    # 业务口径表达式，例如 SUM(revenue)
    formula: Mapped[str] = mapped_column(String(255), default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    metric_type: Mapped[str] = mapped_column(String(16), default="amount")
    relevant_columns: Mapped[str] = mapped_column(Text, default="[]")


class MetaColumnMetric(Base):
    __tablename__ = "meta_column_metric"
    __table_args__ = (
        UniqueConstraint("table_name", "column_name", "metric_name", name="uq_column_metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), index=True)
    column_name: Mapped[str] = mapped_column(String(128), index=True)
    metric_name: Mapped[str] = mapped_column(String(128), index=True)


class MetaValue(Base):
    __tablename__ = "meta_value"
    __table_args__ = (
        UniqueConstraint("table_name", "column_name", "value", name="uq_meta_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(128), index=True)
    column_name: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[str] = mapped_column(String(255), index=True)
    value_desc: Mapped[str] = mapped_column(String(255), default="")
    synonyms: Mapped[str] = mapped_column(Text, default="[]")


class MetaQuestionSql(Base):
    __tablename__ = "meta_question_sql"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(500), index=True)
    sql: Mapped[str] = mapped_column(Text)
    tables_used: Mapped[str] = mapped_column(Text, default="[]")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    # 规则引擎靠 intent 字段做意图路由，例如 org_rank / industry_filter / risk_count
    intent: Mapped[str] = mapped_column(String(64), default="", index=True)
    difficulty: Mapped[str] = mapped_column(String(16), default="easy")
