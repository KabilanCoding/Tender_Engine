"""Tender Tiger auto-analysis: the queue of downloaded tenders waiting to be analysed (filled by n8n after each download).

Additive only: one new table. One row per tender (tid): the documents picked and skipped, the eligibility run, the
outcome, and whether its Microsoft Teams card was sent.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "tt_analysis_queue" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "tt_analysis_queue",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tid", sa.String(40), nullable=False, unique=True),
        # waiting | running | done | failed | stopped | no_documents | skipped
        sa.Column("status", sa.String(20), nullable=False, server_default="waiting"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),     # 1 = closes within 3 days, analysed first
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reason", sa.Text),                                              # why it failed, stopped or was skipped
        sa.Column("stage", sa.String(20)),                                         # last pipeline step reached
        sa.Column("documents", postgresql.JSONB),                                  # picked / skipped files with the reason
        sa.Column("document_id", sa.Integer, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("report_id", sa.Integer),
        sa.Column("verdict", sa.String(20)),
        sa.Column("teams_sent_at", sa.DateTime(timezone=True)),
        sa.Column("teams_error", sa.Text),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_tt_analysis_queue_status", "tt_analysis_queue", ["status", "priority", "created_at"])


def downgrade() -> None:
    op.drop_table("tt_analysis_queue")
