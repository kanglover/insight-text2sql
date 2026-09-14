"""销售经管数仓 ORM 模型（自制的 Text2SQL 数据集）。

建模思路遵循标准星型模型：
- 维度：经营单元、行业、产品线、产品型号、日期
- 事实：收入事实（最细粒度）、目标事实、项目风险事实

金额统一单位为「万元」，方便和 demo 中的口径对齐。
"""

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DimOrg(Base):
    """经营单元：系统部 / 代表处 / 办事处，归属大区。"""

    __tablename__ = "dw_dim_org"

    org_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_code: Mapped[str] = mapped_column(String(32), unique=True)
    org_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    org_level: Mapped[str] = mapped_column(String(16))  # 系统部/代表处/办事处
    region: Mapped[str] = mapped_column(String(16), index=True)  # 大区
    parent_org: Mapped[str] = mapped_column(String(64), default="")


class DimIndustry(Base):
    """行业。"""

    __tablename__ = "dw_dim_industry"

    industry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    industry_name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    industry_group: Mapped[str] = mapped_column(String(32), default="")


class DimProductLine(Base):
    """产品线：通用计算 / 智能计算 / 商业解决方案。"""

    __tablename__ = "dw_dim_product_line"

    product_line_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_line_name: Mapped[str] = mapped_column(String(32), unique=True, index=True)


class DimProduct(Base):
    """产品型号。"""

    __tablename__ = "dw_dim_product"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_line_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_product_line.product_line_id"))
    list_price: Mapped[float] = mapped_column(Float, default=0.0)


class DimDate(Base):
    """日期维度。"""

    __tablename__ = "dw_dim_date"

    date_key: Mapped[int] = mapped_column(Integer, primary_key=True)  # yyyymmdd
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)


class FactRevenue(Base):
    """收入事实：粒度 = 日期 × 经营单元 × 行业 × 产品。"""

    __tablename__ = "dw_fact_revenue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_org.org_id"), index=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_industry.industry_id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_product.product_id"), index=True)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)  # 收入（万元）
    contract_amount: Mapped[float] = mapped_column(Float, default=0.0)  # 合同额（万元）
    collection_amount: Mapped[float] = mapped_column(Float, default=0.0)  # 回款（万元）
    order_count: Mapped[int] = mapped_column(Integer, default=0)  # 订单数


class FactTarget(Base):
    """目标事实：粒度 = 年份 × 经营单元 × 产品线。"""

    __tablename__ = "dw_fact_target"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_org.org_id"), index=True)
    product_line_id: Mapped[int] = mapped_column(
        ForeignKey("dw_dim_product_line.product_line_id"), index=True
    )
    biz_target: Mapped[float] = mapped_column(Float, default=0.0)  # 商业目标（万元）
    sol_target: Mapped[float] = mapped_column(Float, default=0.0)  # 商解目标（万元）


class FactProjectRisk(Base):
    """项目风险事实。"""

    __tablename__ = "dw_fact_project_risk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(String(128))
    org_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_org.org_id"), index=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("dw_dim_industry.industry_id"), index=True)
    risk_level: Mapped[str] = mapped_column(String(16), index=True)  # 高/中/低
    risk_type: Mapped[str] = mapped_column(String(32), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="跟进中")
    created_date: Mapped[date] = mapped_column(Date)
