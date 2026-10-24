"""Store chunk embeddings as float arrays (like kb_passage) instead of JSON text

tender_chunks.embedding and project_document_chunks.embedding held the vector as a text string "[0.1,0.2,...]". An array is
smaller, needs no parsing and matches the knowledge-base index. Existing text is converted; nothing is lost.

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("tender_chunks", "project_document_chunks")


def upgrade() -> None:
    for t in _TABLES:
        op.execute(
            f"ALTER TABLE {t} ALTER COLUMN embedding TYPE double precision[] USING "
            "CASE WHEN embedding IS NULL OR btrim(embedding) IN ('', '[]') THEN NULL "
            "ELSE string_to_array(btrim(embedding, '[] '), ',')::double precision[] END")


def downgrade() -> None:
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN embedding TYPE text USING "
                   "CASE WHEN embedding IS NULL THEN NULL ELSE '[' || array_to_string(embedding, ',') || ']' END")
