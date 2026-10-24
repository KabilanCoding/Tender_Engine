"""
Copy documents still kept on this machine to the file server and point the database at the new copies.

Runs on every ./run and does nothing until Settings > System > Document storage is "file server". Safe to run again: a file
already on the file server is skipped. The local copies are left in place (the database no longer uses them); delete the
uploads folder by hand once you have checked the documents open.

Usage (from backend/): python -m scripts.move_documents
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import file_store, runtime_settings
from app.core.config import settings

# table, path column, folder in the storage (SQL giving the folder parts), name to keep
SOURCES = [
    ("kb_files", "file_path", "ARRAY['kb', owner_type, owner_key]", "original_filename"),
    ("project_documents", "file_path", "ARRAY['kb', 'project', project_id::text, doc_category]", "original_filename"),
    ("documents", "file_path", "ARRAY['tenders']", "original_filename"),
    ("proposals", "docx_path", "ARRAY['proposals', document_id::text]", None),
    ("proposals", "pdf_path", "ARRAY['proposals', document_id::text]", None),
]


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    Session = async_sessionmaker(engine)
    async with Session() as db:
        await runtime_settings.load_saved(db)
        if not file_store.on_server():
            print("Document storage is 'local' (Settings > System): nothing to move.")
            await engine.dispose()
            return
        try:
            await file_store.check()
        except file_store.StorageError as e:
            print(f"Documents not moved: {e}")
            await engine.dispose()
            return

        moved = failed = 0
        for table, column, folder_sql, name_col in SOURCES:
            rows = (await db.execute(text(
                f"SELECT id, {column} AS path, {folder_sql} AS folder{', ' + name_col + ' AS name' if name_col else ''} "
                f"FROM {table} WHERE {column} IS NOT NULL AND {column} <> ''"))).mappings().all()
            for r in rows:
                old = r["path"]
                if not file_store.is_local(old):
                    continue                                   # already on the file server, or the file is gone
                try:
                    with open(old, "rb") as fh:
                        data = fh.read()
                    name = r.get("name") or os.path.basename(old)
                    new = await file_store.save([p for p in r["folder"] if p], name, data)
                except Exception as e:
                    failed += 1
                    print(f"  could not move {table}.{column} id {r['id']} ({old}): {e}")
                    continue
                await db.execute(text(f"UPDATE {table} SET {column} = :new WHERE id = :id"), {"new": new, "id": r["id"]})
                if table == "kb_files":                     # the certificate's own copy of the path
                    await db.execute(text("UPDATE certifications SET document_path = :new WHERE document_path = :old"),
                                     {"new": new, "old": old})
                await db.commit()
                moved += 1
                print(f"  {table} id {r['id']}: {old} -> {new}")
        print(f"Documents moved to the file server: {moved}" + (f", failed: {failed}" if failed else "") + ".")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
