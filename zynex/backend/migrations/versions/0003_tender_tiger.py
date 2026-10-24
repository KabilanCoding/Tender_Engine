"""tt_tenders, tt_tender_files, tt_failures for Tender Tiger integration

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    existing_tables = set(insp.get_table_names())

    if "tt_failures" not in existing_tables:
        op.create_table(
            "tt_failures",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tid", sa.Text(), nullable=True),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("failed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "tt_tender_files" not in existing_tables:
        op.create_table(
            "tt_tender_files",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tid", sa.Text(), nullable=False),
            sa.Column("file_name", sa.Text(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("size", sa.BigInteger(), nullable=True),
            sa.Column("sha256", sa.Text(), nullable=True),
            sa.Column("content", sa.LargeBinary(), nullable=True),
            sa.Column("stored_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tid", "kind", "file_name", name="tt_tender_files_tid_kind_file_name_key"),
        )
        op.create_index("tt_tender_files_tid_idx", "tt_tender_files", ["tid"])

    if "tt_tenders" not in existing_tables:
        op.create_table(
            "tt_tenders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tid", sa.Text(), nullable=False),
            sa.Column("organization", sa.Text(), nullable=True),
            sa.Column("dept_tender_number", sa.Text(), nullable=True),
            sa.Column("tender_title", sa.Text(), nullable=True),
            sa.Column("product_description", sa.Text(), nullable=True),
            sa.Column("key_location", sa.Text(), nullable=True),
            sa.Column("tender_type", sa.Text(), nullable=True),
            sa.Column("worth", sa.Text(), nullable=True),
            sa.Column("emd", sa.Text(), nullable=True),
            sa.Column("doc_fees", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Text(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("days_to_go", sa.Integer(), nullable=True),
            sa.Column("startup_relaxation", sa.Text(), nullable=True),
            sa.Column("folder_name", sa.Text(), nullable=True),
            sa.Column("path", sa.Text(), nullable=True),
            sa.Column("files", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("download_status", sa.Text(), nullable=True),
            sa.Column("raw_detail", sa.Text(), nullable=True),
            sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("dept_tender_link", sa.Text(), nullable=True),
            sa.Column("tender_description", sa.Text(), nullable=True),
            sa.Column("department", sa.Text(), nullable=True),
            sa.Column("opening_date", sa.Date(), nullable=True),
            sa.Column("published_date", sa.Date(), nullable=True),
            sa.Column("tender_link", sa.Text(), nullable=True),
            sa.Column("files_path", sa.Text(), nullable=True),
            sa.Column("zip_path", sa.Text(), nullable=True),
            sa.Column("file_count", sa.Integer(), nullable=True),
            sa.Column("documents_listed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("meta_version", sa.Integer(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("dept_link_type", sa.Text(), nullable=True),
            sa.Column("dept_portal_url", sa.Text(), nullable=True),
            sa.Column("dept_link_hint", sa.Text(), nullable=True),
            sa.Column("files_in_db", sa.Integer(), nullable=True),
            sa.Column("worth_amount", sa.Numeric(), nullable=True),
            sa.Column("emd_amount", sa.Numeric(), nullable=True),
            sa.Column("doc_fee_amount", sa.Numeric(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tid", name="tt_tenders_tid_key"),
        )
        op.create_index("tt_tenders_status_idx", "tt_tenders", ["download_status"])
    else:
        # the table already exists (created by the scraper before this migration): add what the app expects
        have = {c["name"] for c in insp.get_columns("tt_tenders")}
        wanted = [
            ("dept_link_type", sa.Text()), ("dept_portal_url", sa.Text()), ("dept_link_hint", sa.Text()),
            ("files_in_db", sa.Integer()), ("worth_amount", sa.Numeric()), ("emd_amount", sa.Numeric()),
            ("doc_fee_amount", sa.Numeric()),
        ]
        for name, kind in wanted:
            if name not in have:
                op.add_column("tt_tenders", sa.Column(name, kind, nullable=True))
        # fill the numeric amounts from the scraped text ("Rs. 12,50,000"); text that is not one plain number stays NULL
        for text_col, amount_col in (("worth", "worth_amount"), ("emd", "emd_amount"), ("doc_fees", "doc_fee_amount")):
            op.execute(
                f"UPDATE tt_tenders SET {amount_col} = regexp_replace({text_col}, '[^0-9.]', '', 'g')::numeric "
                f"WHERE {amount_col} IS NULL AND {text_col} ~ '^[^0-9]*[0-9][0-9,]*(\.[0-9]+)?[^0-9.]*$'"
            )
        if "tt_tenders_status_idx" not in {i["name"] for i in insp.get_indexes("tt_tenders")}:
            op.create_index("tt_tenders_status_idx", "tt_tenders", ["download_status"])


def downgrade() -> None:
    op.drop_table("tt_tenders")
    op.drop_table("tt_tender_files")
    op.drop_table("tt_failures")

