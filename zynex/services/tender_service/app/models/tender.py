from sqlalchemy import String, Boolean, Text, ForeignKey, JSON, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.models.base import Base, TimestampMixin


class EligibilityStatus(str, enum.Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"


class EligibilityReport(Base, TimestampMixin):
    __tablename__ = "eligibility_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    status: Mapped[EligibilityStatus] = mapped_column(
        Enum(EligibilityStatus), default=EligibilityStatus.PENDING
    )
    criteria: Mapped[dict] = mapped_column(JSON, nullable=True)       # extracted criteria list
    compliance_matrix: Mapped[dict] = mapped_column(JSON, nullable=True)
    missing_documents: Mapped[list] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)


class Proposal(Base, TimestampMixin):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    eligibility_report_id: Mapped[int] = mapped_column(
        ForeignKey("eligibility_reports.id"), nullable=True
    )
    technical_proposal: Mapped[str] = mapped_column(Text, nullable=True)
    commercial_proposal: Mapped[str] = mapped_column(Text, nullable=True)
    company_profile: Mapped[str] = mapped_column(Text, nullable=True)
    sections: Mapped[dict] = mapped_column(JSON, nullable=True)
    docx_path: Mapped[str] = mapped_column(String(1000), nullable=True)
    pdf_path: Mapped[str] = mapped_column(String(1000), nullable=True)
