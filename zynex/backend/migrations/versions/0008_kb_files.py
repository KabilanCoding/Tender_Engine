"""Knowledge base: documents kept for each fact (PAN, GSTIN, CIN ... certificates, financial years)

Additive only: one new table. The files live on disk under UPLOAD_DIR/kb/<owner_type>/<owner_key>/; the table holds their paths.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "kb_files" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "kb_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_type", sa.String(40), nullable=False),
        sa.Column("owner_key", sa.String(120), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kb_files_owner", "kb_files", ["owner_type", "owner_key"])


def downgrade() -> None:
    op.drop_index("ix_kb_files_owner", table_name="kb_files")
    op.drop_table("kb_files")
