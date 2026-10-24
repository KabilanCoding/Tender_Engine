"""Seed demo records for Tender Tiger (tt_tenders and tt_tender_files).

Reads bundled JSON files and inserts tenders and file metadata if they do not already exist.
Run with:
    python -m scripts.seed_tender_tiger
"""
import json
import os
import sys
from datetime import datetime, date
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_SYNC_URL",
    os.getenv("DATABASE_URL", "postgresql://zynex:zynex@localhost:5432/zynex")
).replace("+asyncpg", "")


def parse_date(v):
    if not v:
        return None
    if isinstance(v, (datetime, date)):
        return v
    try:
        return datetime.strptime(v[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def parse_datetime(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(v)
    except Exception:
        return None


def main():
    script_dir = os.path.dirname(__file__)
    tenders_file = os.path.join(script_dir, "tender_tiger_seed.json")
    files_file = os.path.join(script_dir, "tender_tiger_files_seed.json")

    if not os.path.exists(tenders_file):
        print(f"Warning: {tenders_file} not found. Skipping Tender Tiger seed.")
        return

    print("Connecting to database...")
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if tt_tenders table exists
        check = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tt_tenders');"
        )).scalar()
        if not check:
            print("Table 'tt_tenders' does not exist yet. Please run migrations first.")
            return

        # A database that the Tender Tiger downloader (n8n + tt_service) already fills is real data: never add demo rows to it,
        # and never touch tt_tender_files there (it holds the downloaded documents themselves).
        if conn.execute(text("SELECT EXISTS (SELECT 1 FROM tt_tenders)")).scalar():
            print("tt_tenders already has data (filled by the downloader): demo Tender Tiger seed skipped, tt_tender_files left untouched.")
            return

        # 1. Seed tt_tenders
        with open(tenders_file, "r") as f:
            tenders = json.load(f)

        existing_tids = set(conn.execute(text("SELECT tid FROM tt_tenders")).scalars().all())
        new_tenders = [t for t in tenders if t["tid"] not in existing_tids]

        if new_tenders:
            print(f"Seeding {len(new_tenders)} new Tender Tiger records into tt_tenders...")
            for t in new_tenders:
                conn.execute(text("""
                    INSERT INTO tt_tenders (
                        tid, organization, dept_tender_number, tender_title, product_description,
                        key_location, tender_type, worth, emd, doc_fees, quantity,
                        due_date, days_to_go, startup_relaxation, folder_name, path,
                        files, download_status, raw_detail, scraped_at, dept_tender_link,
                        tender_description, department, opening_date, published_date,
                        tender_link, files_path, zip_path, file_count, documents_listed,
                        meta_version, first_seen_at, dept_link_type, dept_portal_url,
                        dept_link_hint, files_in_db, worth_amount, emd_amount, doc_fee_amount
                    ) VALUES (
                        :tid, :organization, :dept_tender_number, :tender_title, :product_description,
                        :key_location, :tender_type, :worth, :emd, :doc_fees, :quantity,
                        :due_date, :days_to_go, :startup_relaxation, :folder_name, :path,
                        :files, :download_status, :raw_detail, :scraped_at, :dept_tender_link,
                        :tender_description, :department, :opening_date, :published_date,
                        :tender_link, :files_path, :zip_path, :file_count, :documents_listed,
                        :meta_version, :first_seen_at, :dept_link_type, :dept_portal_url,
                        :dept_link_hint, :files_in_db, :worth_amount, :emd_amount, :doc_fee_amount
                    ) ON CONFLICT (tid) DO NOTHING;
                """), {
                    "tid": t.get("tid"),
                    "organization": t.get("organization"),
                    "dept_tender_number": t.get("dept_tender_number"),
                    "tender_title": t.get("tender_title"),
                    "product_description": t.get("product_description"),
                    "key_location": t.get("key_location"),
                    "tender_type": t.get("tender_type"),
                    "worth": t.get("worth"),
                    "emd": t.get("emd"),
                    "doc_fees": t.get("doc_fees"),
                    "quantity": t.get("quantity"),
                    "due_date": parse_date(t.get("due_date")),
                    "days_to_go": t.get("days_to_go"),
                    "startup_relaxation": t.get("startup_relaxation"),
                    "folder_name": t.get("folder_name"),
                    "path": t.get("path"),
                    "files": json.dumps(t.get("files")) if t.get("files") is not None else None,
                    "download_status": t.get("download_status"),
                    "raw_detail": t.get("raw_detail"),
                    "scraped_at": parse_datetime(t.get("scraped_at")),
                    "dept_tender_link": t.get("dept_tender_link"),
                    "tender_description": t.get("tender_description"),
                    "department": t.get("department"),
                    "opening_date": parse_date(t.get("opening_date")),
                    "published_date": parse_date(t.get("published_date")),
                    "tender_link": t.get("tender_link"),
                    "files_path": t.get("files_path"),
                    "zip_path": t.get("zip_path"),
                    "file_count": t.get("file_count"),
                    "documents_listed": json.dumps(t.get("documents_listed")) if t.get("documents_listed") is not None else None,
                    "meta_version": t.get("meta_version"),
                    "first_seen_at": parse_datetime(t.get("first_seen_at")),
                    "dept_link_type": t.get("dept_link_type"),
                    "dept_portal_url": t.get("dept_portal_url"),
                    "dept_link_hint": t.get("dept_link_hint"),
                    "files_in_db": t.get("files_in_db"),
                    "worth_amount": t.get("worth_amount"),
                    "emd_amount": t.get("emd_amount"),
                    "doc_fee_amount": t.get("doc_fee_amount"),
                })
            conn.commit()
            print(f"Successfully seeded {len(new_tenders)} tenders.")
        else:
            print(f"All {len(tenders)} Tender Tiger records already exist in tt_tenders.")

        # 2. Seed tt_tender_files metadata if file exists
        if os.path.exists(files_file):
            with open(files_file, "r") as f:
                file_records = json.load(f)

            existing_files = set(
                conn.execute(text("SELECT tid || '::' || kind || '::' || file_name FROM tt_tender_files")).scalars().all()
            )
            new_files = [
                fr for fr in file_records
                if f"{fr['tid']}::{fr['kind']}::{fr['file_name']}" not in existing_files
            ]

            if new_files:
                print(f"Seeding {len(new_files)} file metadata records into tt_tender_files...")
                for fr in new_files:
                    conn.execute(text("""
                        INSERT INTO tt_tender_files (
                            tid, file_name, kind, size, sha256
                        ) VALUES (
                            :tid, :file_name, :kind, :size, :sha256
                        ) ON CONFLICT (tid, kind, file_name) DO NOTHING;
                    """), {
                        "tid": fr.get("tid"),
                        "file_name": fr.get("file_name"),
                        "kind": fr.get("kind"),
                        "size": fr.get("size"),
                        "sha256": fr.get("sha256"),
                    })
                conn.commit()
                print(f"Successfully seeded {len(new_files)} file metadata records.")
            else:
                print(f"All {len(file_records)} file metadata records already exist in tt_tender_files.")


if __name__ == "__main__":
    main()

