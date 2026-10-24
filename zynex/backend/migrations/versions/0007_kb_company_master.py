"""Knowledge base: company-master sections (partners, offices, workforce and work-order details, sample flags)

Additive only: new nullable columns and two new tables. Nothing is dropped or renamed.
`is_sample` marks a value that was filled in as a placeholder; the eligibility engine never lets a sample value
decide a pass or fail (it asks for confirmation instead).

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = {
    "employees": [("work_mode", sa.String(50)), ("joining_date", sa.Date()), ("is_key_personnel", sa.Boolean()),
                  ("govt_experience_years", sa.Float()), ("relevant_experience_years", sa.Float())],
    "projects": [("work_order_date", sa.Date()), ("project_role", sa.String(100)), ("evidence_files", sa.JSON())],
    "company_profile": [("is_sample", sa.Boolean())],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, cols in _COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, typ in cols:
            if name not in have:
                op.add_column(table, sa.Column(name, typ, nullable=True))
    tables = insp.get_table_names()
    if "oem_partnerships" not in tables:
        op.create_table(
            "oem_partnerships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("oem", sa.String(200), nullable=False),
            sa.Column("product", sa.String(300), nullable=True),
            sa.Column("partner_type", sa.String(100), nullable=True),
            sa.Column("since_year", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(50), nullable=True),
            sa.Column("territory", sa.String(200), nullable=True),
            sa.Column("authorization_ref", sa.String(300), nullable=True),
            sa.Column("is_sample", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    if "company_offices" not in tables:
        op.create_table(
            "company_offices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("city", sa.String(200), nullable=False),
            sa.Column("state", sa.String(200), nullable=True),
            sa.Column("office_type", sa.String(100), nullable=True),
            sa.Column("tenure", sa.String(50), nullable=True),
            sa.Column("employee_capacity", sa.Integer(), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("is_sample", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("company_offices")
    op.drop_table("oem_partnerships")
    for table, cols in _COLUMNS.items():
        for name, _ in cols:
            op.drop_column(table, name)
