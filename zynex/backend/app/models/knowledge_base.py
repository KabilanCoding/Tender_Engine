from datetime import date
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Boolean, DateTime, String, Integer, Float, Text, Date, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    industry: Mapped[str] = mapped_column(String(200), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    client_code: Mapped[str] = mapped_column(String(50), nullable=True)
    client_type: Mapped[str] = mapped_column(String(200), nullable=True)
    state_region: Mapped[str] = mapped_column(String(200), nullable=True)
    engagement_status: Mapped[str] = mapped_column(String(100), nullable=True)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    client_id: Mapped[int] = mapped_column(nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    technologies: Mapped[list] = mapped_column(JSON, nullable=True)
    team_size: Mapped[int] = mapped_column(Integer, nullable=True)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=True)
    total_value: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    project_code: Mapped[str] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=True)
    completion_date: Mapped[date] = mapped_column(Date, nullable=True)
    domain: Mapped[str] = mapped_column(String(200), nullable=True)
    order_no: Mapped[str] = mapped_column(String(200), nullable=True)
    work_order_date: Mapped[date] = mapped_column(Date, nullable=True)
    project_role: Mapped[str] = mapped_column(String(100), nullable=True)      # main contractor / sub-contractor / consortium member
    evidence_files: Mapped[list] = mapped_column(JSON, nullable=True)           # names of the work-order / completion documents
    portfolio_category: Mapped[str] = mapped_column(String(80), nullable=True)  # GPS & Tracking, IoT & Telemetry, Ticketing ... (portfolio grouping)


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=True)   # junior/mid/senior
    skills: Mapped[list] = mapped_column(JSON, nullable=True)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    employee_code: Mapped[str] = mapped_column(String(50), nullable=True)
    department: Mapped[str] = mapped_column(String(200), nullable=True)
    experience_years: Mapped[float] = mapped_column(Float, nullable=True)
    qualification: Mapped[str] = mapped_column(Text, nullable=True)
    professional_certifications: Mapped[str] = mapped_column(Text, nullable=True)
    work_mode: Mapped[str] = mapped_column(String(50), nullable=True)           # onsite HQ / client site / hybrid
    joining_date: Mapped[date] = mapped_column(Date, nullable=True)
    is_key_personnel: Mapped[bool] = mapped_column(Boolean, nullable=True)
    govt_experience_years: Mapped[float] = mapped_column(Float, nullable=True)
    relevant_experience_years: Mapped[float] = mapped_column(Float, nullable=True)


class Technology(Base, TimestampMixin):
    __tablename__ = "technologies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    proficiency: Mapped[str] = mapped_column(String(50), nullable=True)
    canonical_id: Mapped[str] = mapped_column(String(100), nullable=True)
    experience_years: Mapped[float] = mapped_column(Float, nullable=True)


class Certification(Base, TimestampMixin):
    __tablename__ = "certifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    issuing_body: Mapped[str] = mapped_column(String(300), nullable=True)
    certificate_number: Mapped[str] = mapped_column(String(200), nullable=True)
    valid_until: Mapped[str] = mapped_column(String(50), nullable=True)
    document_path: Mapped[str] = mapped_column(String(1000), nullable=True)
    cert_code: Mapped[str] = mapped_column(String(50), nullable=True)
    issued_on: Mapped[date] = mapped_column(Date, nullable=True)
    valid_until_date: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=True)


class CostParameter(Base, TimestampMixin):
    __tablename__ = "cost_parameters"
    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    qa_percentage: Mapped[float] = mapped_column(Float, default=15.0)
    devops_percentage: Mapped[float] = mapped_column(Float, default=10.0)
    contingency_percentage: Mapped[float] = mapped_column(Float, default=10.0)
    profit_margin_percentage: Mapped[float] = mapped_column(Float, default=20.0)


class CompanyProfile(Base):
    """One registration/identity fact per row (GSTIN, PAN, CIN, address ...). Looked up by key, never searched."""
    __tablename__ = "company_profile"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=True)             # a placeholder value: never decides a pass or fail
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now())


class OemPartnership(Base, TimestampMixin):
    """An authorised-partner / reseller relationship with a product maker (tenders ask for OEM authorisation)."""
    __tablename__ = "oem_partnerships"
    id: Mapped[int] = mapped_column(primary_key=True)
    oem: Mapped[str] = mapped_column(String(200), nullable=False)
    product: Mapped[str] = mapped_column(String(300), nullable=True)
    partner_type: Mapped[str] = mapped_column(String(100), nullable=True)
    since_year: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=True)
    territory: Mapped[str] = mapped_column(String(200), nullable=True)
    authorization_ref: Mapped[str] = mapped_column(String(300), nullable=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=True)


class CompanyOffice(Base, TimestampMixin):
    """Where the company has an office (tenders ask for a local office in a state or city)."""
    __tablename__ = "company_offices"
    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(200), nullable=True)
    office_type: Mapped[str] = mapped_column(String(100), nullable=True)        # registered / corporate / branch / delivery centre
    tenure: Mapped[str] = mapped_column(String(50), nullable=True)              # owned / rented
    employee_capacity: Mapped[int] = mapped_column(Integer, nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, nullable=True)


class KbPassage(Base):
    """Searchable text of one knowledge-base row (a project, an employee ...) and its embedding. Derived data: rebuilt from the tables."""
    __tablename__ = "kb_passage"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_table: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    embedding: Mapped[list] = mapped_column(ARRAY(Float), nullable=True)
    embed_model: Mapped[str] = mapped_column(String(100), nullable=True)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now())


class KbFile(Base):
    """A document kept for a knowledge-base fact: the PAN card for `pan`, the certificate PDF for a certification, an audited
    balance sheet for a financial year. The file is kept in the document storage (this machine or the file server, see
    app.core.file_store) under kb/...; this row holds only its full path."""
    __tablename__ = "kb_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)   # profile | certification | financial | office | oem | client | employee | technology
    owner_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)   # profile field key (e.g. "pan") or the record id
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
