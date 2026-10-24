"""kb_passage: one short text per knowledge-base row, with its embedding, for matching experience by meaning

Embeddings are plain float arrays (no database extension needed, works on any server); the knowledge base is a few
hundred rows, so a search is a few milliseconds.

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_passage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_table", sa.String(50), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(40), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("embed_model", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_table", "source_id", name="uq_kb_passage_source"),
    )


def downgrade() -> None:
    op.drop_table("kb_passage")
