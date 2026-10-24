"""Projects: portfolio category (GPS & Tracking, IoT & Telemetry, Ticketing ...)

Additive only: one nullable column, filled for existing projects from their name, description and technologies.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "portfolio_category" not in {c["name"] for c in sa.inspect(bind).get_columns("projects")}:
        op.add_column("projects", sa.Column("portfolio_category", sa.String(80), nullable=True))
    from app.services.project_category import guess_category
    rows = bind.execute(sa.text("SELECT id, name, description, technologies FROM projects WHERE portfolio_category IS NULL")).mappings().all()
    for r in rows:
        techs = r["technologies"] if isinstance(r["technologies"], list) else []
        bind.execute(sa.text("UPDATE projects SET portfolio_category = :c WHERE id = :id"),
                     {"c": guess_category(r["name"], r["description"], techs), "id": r["id"]})


def downgrade() -> None:
    op.drop_column("projects", "portfolio_category")
