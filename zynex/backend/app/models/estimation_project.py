from sqlalchemy import String, Integer, Text, Float, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class EstimationProject(Base, TimestampMixin):
    __tablename__ = "estimation_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft / finalized
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    # Buffer settings (editable by user)
    complexity_pct: Mapped[float] = mapped_column(Float, default=0.02)
    unit_testing_pct: Mapped[float] = mapped_column(Float, default=0.05)
    rework_pct: Mapped[float] = mapped_column(Float, default=0.10)
    pm_pct: Mapped[float] = mapped_column(Float, default=0.20)
    design_arch_pct: Mapped[float] = mapped_column(Float, default=0.25)
    spec_uiux_pct: Mapped[float] = mapped_column(Float, default=0.15)
    dev_buffer_pct: Mapped[float] = mapped_column(Float, default=0.20)
    margin_pct: Mapped[float] = mapped_column(Float, default=0.20)
    infra_cost: Mapped[float] = mapped_column(Float, default=0.0)

    # Computed summary (stored for quick display)
    total_dev_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_qa_hours: Mapped[float] = mapped_column(Float, default=0.0)
    grand_total_hours: Mapped[float] = mapped_column(Float, default=0.0)
    internal_cost: Mapped[float] = mapped_column(Float, default=0.0)
    margin_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total_project_cost: Mapped[float] = mapped_column(Float, default=0.0)

    # Relationships
    features: Mapped[list["EstimationFeature"]] = relationship(
        "EstimationFeature",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="EstimationFeature.sort_order",
        lazy="selectin",
    )
    resources: Mapped[list["EstimationResource"]] = relationship(
        "EstimationResource",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class EstimationFeature(Base):
    __tablename__ = "estimation_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("estimation_projects.id", ondelete="CASCADE")
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    milestone: Mapped[str] = mapped_column(String(200), nullable=True)
    module: Mapped[str] = mapped_column(String(200), nullable=True)
    sub_module: Mapped[str] = mapped_column(String(200), nullable=True)
    feature: Mapped[str] = mapped_column(String(500))

    # Complexity per component: "simple" | "medium" | "complex" | None
    data_model_complexity: Mapped[str] = mapped_column(String(20), nullable=True)
    api_complexity: Mapped[str] = mapped_column(String(20), nullable=True)
    business_rules_complexity: Mapped[str] = mapped_column(String(20), nullable=True)
    ui_complexity: Mapped[str] = mapped_column(String(20), nullable=True)
    fixed_hours: Mapped[float] = mapped_column(Float, default=0.0)

    # Calculated (recalculated on save)
    base_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_dev_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_qa_hours: Mapped[float] = mapped_column(Float, default=0.0)
    total_hours: Mapped[float] = mapped_column(Float, default=0.0)

    project: Mapped["EstimationProject"] = relationship(
        "EstimationProject", back_populates="features"
    )


class EstimationResource(Base):
    __tablename__ = "estimation_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("estimation_projects.id", ondelete="CASCADE")
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(200))
    responsibility: Mapped[str] = mapped_column(String(500), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    effort_hours: Mapped[float] = mapped_column(Float, default=0.0)
    effort_pct: Mapped[float] = mapped_column(Float, default=0.0)
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')

    project: Mapped["EstimationProject"] = relationship(
        "EstimationProject", back_populates="resources"
    )
