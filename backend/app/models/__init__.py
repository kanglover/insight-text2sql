"""统一导出所有 ORM 模型，保证 Base.metadata 完整。"""

from app.models.biz import (
    AppSetting,
    ChatMessage,
    ChatSession,
    Feedback,
    ModelSetting,
    QueryLog,
)
from app.models.dw import (
    DimDate,
    DimIndustry,
    DimOrg,
    DimProduct,
    DimProductLine,
    FactProjectRisk,
    FactRevenue,
    FactTarget,
)
from app.models.meta import (
    MetaColumn,
    MetaColumnMetric,
    MetaMetric,
    MetaQuestionSql,
    MetaTable,
    MetaValue,
)

__all__ = [
    # 元数据知识库
    "MetaTable",
    "MetaColumn",
    "MetaMetric",
    "MetaColumnMetric",
    "MetaValue",
    "MetaQuestionSql",
    # 数仓
    "DimOrg",
    "DimIndustry",
    "DimProductLine",
    "DimProduct",
    "DimDate",
    "FactRevenue",
    "FactTarget",
    "FactProjectRisk",
    # 业务库
    "ChatSession",
    "ChatMessage",
    "QueryLog",
    "Feedback",
    "AppSetting",
    "ModelSetting",
]
