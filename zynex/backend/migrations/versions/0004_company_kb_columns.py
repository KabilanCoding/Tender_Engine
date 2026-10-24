"""Company knowledge base: columns the eligibility engine needs, plus company_profile

Adds only what the engine reads (dates, domain, net worth, registrations). Nothing is dropped or renamed,
so existing rows and screens keep working.

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = {
    "clients": [("client_code", sa.String(50)), ("client_type", sa.String(200)), ("state_region", sa.String(200)),
                ("engagement_status", sa.String(100))],
    "projects": [("project_code", sa.String(50)), ("start_date", sa.Date()), ("completion_date", sa.Date()),
                 ("domain", sa.String(200)), ("order_no", sa.String(200))],
    "employees": [("employee_code", sa.String(50)), ("department", sa.String(200)), ("experience_years", sa.Float()),
                  ("qualification", sa.Text()), ("professional_certifications", sa.Text())],
    "technologies": [("canonical_id", sa.String(100)), ("experience_years", sa.Float())],
    "certifications": [("cert_code", sa.String(50)), ("issued_on", sa.Date()), ("valid_until_date", sa.Date()),
                       ("status", sa.String(50))],
    "financial_records": [("net_worth", sa.Float()), ("working_capital", sa.Float()), ("ebitda", sa.Float()),
                          ("gross_assets", sa.Float()), ("total_liabilities", sa.Float()), ("current_ratio", sa.Float()),
                          ("audit_firm", sa.String(300)), ("audit_signoff_date", sa.Date())],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, cols in _COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, typ in cols:
            if name not in have:
                op.add_column(table, sa.Column(name, typ, nullable=True))
    for table, col in (("clients", "client_code"), ("projects", "project_code"), ("employees", "employee_code"),
                       ("certifications", "cert_code")):
        op.create_index(f"uq_{table}_{col}", table, [col], unique=True, postgresql_where=sa.text(f"{col} IS NOT NULL"))
    op.create_index("uq_financial_records_fiscal_year", "financial_records", ["fiscal_year"], unique=True)

    if "company_profile" not in insp.get_table_names():
        op.create_table(
            "company_profile",
            sa.Column("key", sa.String(100), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )


def downgrade() -> None:
    op.drop_table("company_profile")
    op.drop_index("uq_financial_records_fiscal_year", table_name="financial_records")
    for table, col in (("clients", "client_code"), ("projects", "project_code"), ("employees", "employee_code"),
                       ("certifications", "cert_code")):
        op.drop_index(f"uq_{table}_{col}", table_name=table)
    for table, cols in _COLUMNS.items():
        for name, _ in cols:
            op.drop_column(table, name)
