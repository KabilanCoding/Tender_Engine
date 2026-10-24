"""Tender Tiger: per-user viewed / read marks

Additive only: one new table. A row means this user has opened the tender (viewed_at) and, optionally, marked it read (read_at).

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "tt_tender_reads" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "tt_tender_reads",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("tid", sa.String(40), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("tt_tender_reads")
