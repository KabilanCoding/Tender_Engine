"""Delete ALL knowledge-base records. DESTRUCTIVE: local development only.

Usage (from backend/):  python -m scripts.clear_kb --yes
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402

TABLES = [
    "project_document_chunks", "project_documents", "tender_chunks", "certifications", "technologies",
    "employees", "projects", "clients", "financial_records",
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for table in TABLES:
            await db.execute(text(f"DELETE FROM {table}"))
        await db.commit()
    print("knowledge base cleared")


if __name__ == "__main__":
    if "--yes" not in sys.argv:
        sys.exit("This deletes every knowledge-base record. Re-run with --yes to confirm.")
    asyncio.run(main())
