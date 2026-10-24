from sqlalchemy import String, Integer, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class EstimationReport(Base, TimestampMixin):
    __tablename__ = "estimation_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    modules_count: Mapped[int] = mapped_column(Integer, default=0)
    total_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_weeks: Mapped[int] = mapped_column(Integer, default=0)
    modules: Mapped[dict] = mapped_column(JSON, nullable=True)   # structured module breakdown
    sprints: Mapped[dict] = mapped_column(JSON, nullable=True)   # sprint plan
    tasks: Mapped[dict] = mapped_column(JSON, nullable=True)     # task list with effort

    cost_sheet: Mapped["CostSheet"] = relationship(
        back_populates="estimation", uselist=False, lazy="selectin"
    )


class CostSheet(Base, TimestampMixin):
    __tablename__ = "cost_sheets"

    id: Mapped[int] = mapped_column(primary_key=True)
    estimation_id: Mapped[int] = mapped_column(
        ForeignKey("estimation_reports.id"), nullable=False
    )
    developer_cost: Mapped[float] = mapped_column(Float, default=0.0)
    qa_cost: Mapped[float] = mapped_column(Float, default=0.0)
    devops_cost: Mapped[float] = mapped_column(Float, default=0.0)
    infrastructure_cost: Mapped[float] = mapped_column(Float, default=0.0)
    storage_cost: Mapped[float] = mapped_column(Float, default=0.0)
    contingency: Mapped[float] = mapped_column(Float, default=0.0)
    profit_margin: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    suggested_bid: Mapped[float] = mapped_column(Float, default=0.0)
    line_items: Mapped[dict] = mapped_column(JSON, nullable=True)

    estimation: Mapped["EstimationReport"] = relationship(back_populates="cost_sheet")
