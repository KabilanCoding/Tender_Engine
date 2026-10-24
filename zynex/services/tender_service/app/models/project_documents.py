from sqlalchemy import String, Integer, Float, Text, Boolean, ForeignKey, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from app.models.base import Base
from datetime import datetime


class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_turnover: Mapped[float] = mapped_column(Float, nullable=False)
    net_profit: Mapped[float] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    net_worth: Mapped[float] = mapped_column(Float, nullable=True)
    working_capital: Mapped[float] = mapped_column(Float, nullable=True)
    ebitda: Mapped[float] = mapped_column(Float, nullable=True)
    gross_assets: Mapped[float] = mapped_column(Float, nullable=True)
    total_liabilities: Mapped[float] = mapped_column(Float, nullable=True)
    current_ratio: Mapped[float] = mapped_column(Float, nullable=True)
    audit_firm: Mapped[str] = mapped_column(String(300), nullable=True)
    audit_signoff_date = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectDocument(Base):
    __tablename__ = "project_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_category: Mapped[str] = mapped_column(String(50), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_error: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list["ProjectDocumentChunk"]] = relationship(
        "ProjectDocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProjectDocumentChunk(Base):
    __tablename__ = "project_document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_documents.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str] = mapped_column(String(500), nullable=True)
    doc_category: Mapped[str] = mapped_column(String(50), nullable=True)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # embedding: a float array (same format as kb_passage)
    # We read/write it as a string "[0.1, 0.2, ...]" and let pgvector handle it
    embedding: Mapped[list] = mapped_column(ARRAY(Float), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["ProjectDocument"] = relationship(
        "ProjectDocument", back_populates="chunks"
    )


class TenderChunk(Base):
    __tablename__ = "tender_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str] = mapped_column(String(500), nullable=True)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list] = mapped_column(ARRAY(Float), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
