"""Tender Tiger: the scraped tender notices (tt_tenders) and their files (read from the downloader's folder on disk), shown inside Tender Analysis.

Read-only over the tt_* tables, which are not managed by Alembic. The one write is "Analyse", which copies a stored
PDF/DOCX into the normal uploads folder and starts the same eligibility run an upload would (see tender.upload_tender).
"""
import asyncio
import re
import csv
import io
import os
import zipfile
import urllib.parse
import httpx
import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tender.run_options import RunOptions
from app.api.v1.eligibility import check_model_available, start_run
from app.core import file_store
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import decode_token, oauth2_scheme
from app.models.document import Document, DocumentStatus, DocumentType
from app.parsers.parser_factory import get_parser
from app.services.eligibility.errors import FileValidationError
from app.services.eligibility.file_validator import FileValidator

router = APIRouter(prefix="/tender-tiger", tags=["tender-tiger"])

_ANALYSABLE = {".pdf", ".docx", ".txt"}
_MAX_TEXT = 300_000                # characters sent to the viewer
_MAX_ZIP_ENTRY = 100 * 1024 * 1024  # largest file opened from inside a zip
_NO_VALUE = {"", "ref doc", "refer document", "n/a", "na", "-", "--"}
_LIST_COLUMNS = """tid, tender_title, organization, department, key_location, tender_type, worth, worth_amount,
    emd, emd_amount, doc_fees, doc_fee_amount, due_date, published_date, opening_date, file_count, files_in_db,
    tender_link, COALESCE(first_seen_at, scraped_at) AS downloaded_at, scraped_at AS updated_at"""
_DETAIL_COLUMNS = _LIST_COLUMNS + """, product_description, tender_description, dept_tender_number, quantity,
    startup_relaxation, dept_tender_link, dept_portal_url, download_status, scraped_at"""


def _clean(value: Any) -> Optional[str]:
    """Raw scraped text, or None when it only says 'see the document'."""
    s = " ".join(str(value or "").split())
    return None if s.lower() in _NO_VALUE else s


_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(crore|cr\b|lakh|lac|l\b)?", re.IGNORECASE)


def _amount(text: Optional[str]) -> Optional[float]:
    """'₹ 22289050.0' -> 22289050; '₹ 10.00 Lakh' -> 1000000; 'Ref Doc' -> None (the downloader fills the number column only sometimes)."""
    m = _AMOUNT.search(str(text or ""))
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    return n * 1e7 if unit.startswith("cr") else n * 1e5 if unit.startswith(("lakh", "lac", "l")) else n


def _amount_sql(col: str, num_col: str) -> str:
    """The same rule in SQL, so sorting by value or EMD works when only the text is filled."""
    digits = f"NULLIF(substring(replace({col}, ',', '') from '[0-9]+(?:\\.[0-9]+)?'), '')::numeric"
    return (f"COALESCE({num_col}, CASE WHEN {col} ~* 'crore|\\mcr\\M' THEN {digits} * 10000000 "
            f"WHEN {col} ~* 'lakh|\\mlac\\M' THEN {digits} * 100000 ELSE {digits} END)")


def _row(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: (v.isoformat() if isinstance(v, date) else float(v) if hasattr(v, "as_tuple") else v) for k, v in r.items()}
    for key in ("worth", "emd", "doc_fees"):
        out[key] = _clean(r.get(key))
    for key, num in (("worth", "worth_amount"), ("emd", "emd_amount"), ("doc_fees", "doc_fee_amount")):
        if num in out and out.get(num) is None:
            out[num] = _amount(out.get(key))
    for key in ("tender_title", "organization", "department", "key_location", "tender_type", "quantity",
                "dept_tender_number", "startup_relaxation", "tender_description", "product_description"):
        if key in out:
            out[key] = _clean(r.get(key))
    return out


_SORTS = {
    "downloaded_desc": "COALESCE(first_seen_at, scraped_at) DESC NULLS LAST, id DESC",
    "due_desc": "due_date DESC NULLS LAST, id DESC",
    "due_asc": "due_date ASC NULLS LAST, id DESC",
    "published_desc": "published_date DESC NULLS LAST, id DESC",
    "value_desc": f"{_amount_sql('worth', 'worth_amount')} DESC NULLS LAST, due_date DESC NULLS LAST",
    "value_asc": f"{_amount_sql('worth', 'worth_amount')} ASC NULLS LAST, due_date DESC NULLS LAST",
    "emd_desc": f"{_amount_sql('emd', 'emd_amount')} DESC NULLS LAST, due_date DESC NULLS LAST",
    "published_asc": "published_date ASC NULLS LAST, id DESC",
    "downloaded_asc": "COALESCE(first_seen_at, scraped_at) ASC NULLS LAST, id DESC",
    "title_desc": "lower(tender_title) DESC NULLS LAST, id DESC",
    "title_asc": "lower(tender_title) ASC NULLS LAST, id DESC",
}
_VERDICT = {"ELIGIBLE": "PASS", "NOT_ELIGIBLE": "FAIL", "PARTIAL": "PARTIAL", "PENDING": "PARTIAL"}


def _user(token: str) -> int:
    try:
        return int(decode_token(token).get("sub") or 0)
    except Exception:
        return 0


def _filters(search: str, status: str, org: str, read: str = "all", user_id: int = 0) -> tuple:
    where, params = ["1=1"], {"today": date.today(), "uid": user_id}
    # per-user marks: new = never opened, viewed = opened but not marked read, read = marked read
    if read == "new":
        where.append("NOT EXISTS (SELECT 1 FROM tt_tender_reads r WHERE r.user_id = :uid AND r.tid = tt_tenders.tid)")
    elif read == "unread":
        where.append("NOT EXISTS (SELECT 1 FROM tt_tender_reads r WHERE r.user_id = :uid AND r.tid = tt_tenders.tid AND r.read_at IS NOT NULL)")
    elif read == "read":
        where.append("EXISTS (SELECT 1 FROM tt_tender_reads r WHERE r.user_id = :uid AND r.tid = tt_tenders.tid AND r.read_at IS NOT NULL)")
    if search.strip():
        params["q"] = f"%{search.strip()}%"
        where.append("(tender_title ILIKE :q OR organization ILIKE :q OR department ILIKE :q OR tid ILIKE :q "
                     "OR key_location ILIKE :q OR dept_tender_number ILIKE :q)")
    if org.strip():
        params["org"] = org.strip()
        where.append("organization = :org")
    if status == "open":
        where.append("due_date >= :today")
    elif status == "soon":
        where.append("due_date BETWEEN :today AND :today + 7")
    elif status == "closed":
        where.append("due_date < :today")
    return " AND ".join(where), params


async def _last_runs(db: AsyncSession, names: List[str]) -> Dict[str, Dict[str, Any]]:
    """Latest eligibility run for each file name that has been analysed before: {file_name: {...}}."""
    if not names:
        return {}
    rows = (await db.execute(text(
        "SELECT DISTINCT ON (d.original_filename) d.original_filename AS name, r.id AS run_id, r.status::text AS status, "
        "COALESCE(r.compliance_matrix::jsonb->>'state', 'DONE') AS state, r.created_at, "
        "r.compliance_matrix::jsonb->'counts'->>'pass' AS met, r.compliance_matrix::jsonb->'counts'->>'total' AS total "
        "FROM eligibility_reports r JOIN documents d ON d.id = r.document_id "
        "WHERE d.original_filename = ANY(:names) ORDER BY d.original_filename, r.created_at DESC"),
        {"names": names})).mappings().all()
    # met / total let the screen tell "partially eligible" (some requirements met) from "cannot confirm yet" (none confirmed)
    return {r["name"]: {"run_id": str(r["run_id"]), "state": r["state"], "verdict": _VERDICT.get(r["status"]),
                        "met": int(r["met"]) if r["met"] and str(r["met"]).isdigit() else None,
                        "total": int(r["total"]) if r["total"] and str(r["total"]).isdigit() else None,
                        "at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows}


@router.get("/tenders")
async def list_tenders(
    search: str = Query("", max_length=100),
    status: str = Query("all", pattern="^(all|open|soon|closed)$"),
    org: str = Query("", max_length=200),
    sort: str = Query("due_desc", pattern="^(downloaded_desc|downloaded_asc|due_desc|due_asc|published_desc|published_asc|value_desc|value_asc|emd_desc|title_asc|title_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    read: str = Query("all", pattern="^(all|new|unread|read)$"),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    uid = _user(token)
    try:
        clause, params = _filters(search, status, org, read, uid)
        params.update({"limit": page_size, "offset": (page - 1) * page_size})
        total = (await db.execute(text(f"SELECT count(*) FROM tt_tenders WHERE {clause}"), params)).scalar_one()
        rows = (await db.execute(text(
            f"SELECT {_LIST_COLUMNS} FROM tt_tenders WHERE {clause} "
            f"ORDER BY {_SORTS[sort]} LIMIT :limit OFFSET :offset"), params)).mappings().all()
        items = [_row(dict(r)) for r in rows]

        files = await _file_names(db, [i["tid"] for i in items])
        runs = await _last_runs(db, [f["file_name"] for f in files])
        by_tid: Dict[str, List[Dict[str, Any]]] = {}
        for f in files:
            if f["file_name"] in runs:
                by_tid.setdefault(f["tid"], []).append(runs[f["file_name"]])
        for i in items:
            found = sorted(by_tid.get(i["tid"], []), key=lambda r: r["at"] or "", reverse=True)
            i["last_run"] = found[0] if found else None
            i["analysed_files"] = len(found)
        marks = {m["tid"]: m for m in (await db.execute(text(
            "SELECT tid, viewed_at, read_at FROM tt_tender_reads WHERE user_id = :uid AND tid = ANY(:tids)"),
            {"uid": uid, "tids": [i["tid"] for i in items]})).mappings().all()}
        for i in items:
            m = marks.get(i["tid"])
            i["seen"] = "read" if m and m["read_at"] else "viewed" if m else "new"

        summary = (await db.execute(text(
            "SELECT count(*) AS total, count(*) FILTER (WHERE due_date >= :today) AS open, "
            "count(*) FILTER (WHERE due_date BETWEEN :today AND :today + 7) AS closing_soon, "
            "count(DISTINCT organization) AS organizations, "
            "count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM tt_tender_reads r WHERE r.user_id = :uid AND r.tid = tt_tenders.tid)) AS new, "
            "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM tt_tender_reads r WHERE r.user_id = :uid AND r.tid = tt_tenders.tid AND r.read_at IS NOT NULL)) AS read "
            "FROM tt_tenders"), {"today": date.today(), "uid": uid})).mappings().one()
        return {"items": items, "total": total, "page": page, "page_size": page_size, "summary": dict(summary)}
    except Exception as e:
        logger.warning(f"Error querying tt_tenders (table may not exist or is empty): {e}")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "summary": {"total": 0, "open": 0, "closing_soon": 0, "organizations": 0},
            "error": "Tender Tiger database tables not initialized yet. Please run migrations."
        }


@router.get("/organizations")
async def organizations(db: AsyncSession = Depends(get_db)):
    try:
        rows = (await db.execute(text(
            "SELECT organization, count(*) AS n FROM tt_tenders WHERE organization IS NOT NULL AND organization <> '' "
            "GROUP BY organization ORDER BY organization"))).mappings().all()
        return [{"name": r["organization"], "count": r["n"]} for r in rows]
    except Exception as e:
        logger.warning(f"Error querying tt_tenders organizations: {e}")
        return []


@router.get("/export")
async def export_csv(
    search: str = Query("", max_length=100),
    status: str = Query("all", pattern="^(all|open|soon|closed)$"),
    org: str = Query("", max_length=200),
    sort: str = Query("due_desc", pattern="^(downloaded_desc|downloaded_asc|due_desc|due_asc|published_desc|published_asc|value_desc|value_asc|emd_desc|title_asc|title_desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """The tenders matching the current filters as a CSV file (opens in Excel)."""
    clause, params = _filters(search, status, org)
    rows = (await db.execute(text(
        f"SELECT tid, tender_title, organization, department, key_location, worth_amount, emd_amount, doc_fee_amount, "
        f"published_date, due_date, opening_date, file_count, tender_link FROM tt_tenders WHERE {clause} "
        f"ORDER BY {_SORTS[sort]}"), params)).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Tender ID", "Title", "Organization", "Department", "Location", "Value (INR)", "EMD (INR)",
                "Document fee (INR)", "Published", "Due date", "Opening date", "Files", "Link"])
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return Response(content="\ufeff" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="tender-tiger-tenders.csv"'})


@router.get("/tenders/{tid}")
async def tender_detail(tid: str, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    row = (await db.execute(text(f"SELECT {_DETAIL_COLUMNS} FROM tt_tenders WHERE tid = :tid"), {"tid": tid})).mappings().first()
    if row is None:
        raise HTTPException(404, "Tender not found")
    # opening a tender marks it viewed for this user (a GET with a small side effect, by design: "opened = viewed")
    uid = _user(token)
    mark = None
    if uid:
        mark = (await db.execute(text(
            "INSERT INTO tt_tender_reads (user_id, tid) VALUES (:uid, :tid) "
            "ON CONFLICT (user_id, tid) DO UPDATE SET viewed_at = tt_tender_reads.viewed_at RETURNING read_at"),
            {"uid": uid, "tid": tid})).mappings().first()
        await db.commit()
    files = [{k: f[k] for k in ("id", "file_name", "kind", "size", "on_disk")} for f in await _tender_files(db, tid)]
    out = _row(dict(row))
    out["scraped_at"] = row["scraped_at"].isoformat() if row["scraped_at"] else None
    out["seen"] = "read" if mark and mark["read_at"] else "viewed" if uid else "new"
    runs = await _last_runs(db, [f["file_name"] for f in files])
    out["files"] = [{**dict(f), "analysable": os.path.splitext(f["file_name"])[1].lower() in _ANALYSABLE
                     and f["kind"] != "zip", "last_run": runs.get(f["file_name"])} for f in files]
    return out


# ── Tender files live in the downloader's folder on the file server (never in the database) ───────────────────────────
#   tt_tenders.files_path = <TT_DOCS_DIR>/<tid>_<org>_<title>/files   (every unzipped file, flat)
#   tt_tenders.zip_path   = <TT_DOCS_DIR>/<tid>_<org>_<title>/<..>_AllDocuments.zip
# Read from this machine's disk when the folder is here, otherwise through the downloader's helper (TT_SERVICE_URL).

def _local_path(stored: Optional[str]) -> Optional[str]:
    """Paths saved by the downloader on its own machine; TENDER_DOCS_DIR (optional) maps them to this server's copy of the folder."""
    if not stored:
        return None
    root = getattr(settings, "TENDER_DOCS_DIR", "") or os.path.expanduser("~/Tendo_Docs")   # default: the downloader's own default folder
    if root and not os.path.exists(stored):
        parts = stored.replace("\\", "/").split("/")
        for i in range(len(parts)):                    # keep "<tender folder>/files/<name>", swap the root in front of it
            cand = os.path.join(root, *parts[i:])
            if os.path.exists(cand):
                return cand
    return stored


async def _file_names(db: AsyncSession, tids: List[str]) -> List[Dict[str, Any]]:
    """[{tid, file_name}] for many tenders, from the file list the downloader recorded in tt_tenders.files."""
    if not tids:
        return []
    rows = (await db.execute(text("SELECT tid, files FROM tt_tenders WHERE tid = ANY(:tids)"), {"tids": tids})).mappings().all()
    out = []
    for r in rows:
        for f in (r["files"] or []):
            name = os.path.basename(str((f or {}).get("name") or ""))
            if name:
                out.append({"tid": r["tid"], "file_name": name})
    return out


async def _tender_files(db: AsyncSession, tid: str) -> List[Dict[str, Any]]:
    """Every file of one tender: the original zip first, then the unzipped files, each with a stable id "<tid>.<n>"."""
    t = (await db.execute(text("SELECT files_path, zip_path, files FROM tt_tenders WHERE tid = :tid"), {"tid": tid})).mappings().first()
    if t is None:
        return []

    folder, zip_path = _local_path(t["files_path"]), _local_path(t["zip_path"])
    found: List[Dict[str, Any]] = []

    # 1. Zip file (from t["zip_path"])
    zip_name = os.path.basename(zip_path) if zip_path else None
    if zip_name:
        found.append({"file_name": zip_name, "kind": "zip", "path": zip_path})

    # 2. Files listed in folder or tt_tenders.files
    seen_names = {zip_name} if zip_name else set()
    if folder and os.path.isdir(folder):
        names = sorted(n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)))
    else:                                              # folder not on this server: list what the downloader recorded
        names = sorted(os.path.basename(str((f or {}).get("name") or "")) for f in (t["files"] or []) if (f or {}).get("name"))
    for n in names:
        if n and n not in seen_names:
            seen_names.add(n)
            found.append({"file_name": n, "kind": "file", "path": os.path.join(folder, n) if folder else None})

    has_service = bool(getattr(settings, "TT_SERVICE_URL", ""))
    for i, f in enumerate(found):
        f["id"] = f"{tid}.{i}"
        has_disk = bool(f["path"] and os.path.isfile(f["path"]))
        # Available on server if remote service is configured or files exist on server disk
        f["on_disk"] = has_service or has_disk
        if has_disk:
            f["size"] = os.path.getsize(f["path"])
        else:
            file_meta = next((item for item in (t["files"] or []) if (item or {}).get("name") and os.path.basename(item["name"]) == f["file_name"]), None)
            f["size"] = (file_meta or {}).get("size") if file_meta else None
    return found


async def _file(db: AsyncSession, file_id: str):
    tid, _, idx = file_id.rpartition(".")
    if not tid or not idx.isdigit():
        raise HTTPException(404, "File not found")
    files = await _tender_files(db, tid)
    if int(idx) >= len(files):
        raise HTTPException(404, "File not found")
    f = files[int(idx)]
    if not f["on_disk"]:
        raise HTTPException(404, f"The file {f['file_name']} is not available on the server.")

    data: Optional[bytes] = None

    # 1. Fetch exclusively from the Ubuntu server helper (tt_service on 10.10.10.19:8787)
    if getattr(settings, "TT_SERVICE_URL", ""):
        base_url = settings.TT_SERVICE_URL.rstrip("/")
        headers = {}
        if getattr(settings, "TT_SERVICE_TOKEN", ""):
            headers["x-token"] = settings.TT_SERVICE_TOKEN
        encoded_name = urllib.parse.quote(f["file_name"])
        url = f"{base_url}/d/{tid}/original.zip" if f["kind"] == "zip" else f"{base_url}/d/{tid}/f/{encoded_name}"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.content
                else:
                    logger.warning(f"TT_SERVICE_URL {url} returned HTTP {res.status_code}")
        except Exception as e:
            logger.warning(f"Failed to fetch file from TT_SERVICE_URL: {e}")

    # 2. Or if running directly on the Ubuntu server itself (read from server disk folder)
    if data is None and f.get("path") and os.path.isfile(f["path"]):
        with open(f["path"], "rb") as fh:
            data = fh.read()

    if data is None:
        raise HTTPException(404, f"The file {f['file_name']} could not be loaded from the server.")
    return {**f, "tid": tid, "content": data}


def _media(name: str) -> str:
    return {"pdf": "application/pdf", "zip": "application/zip", "txt": "text/plain; charset=utf-8",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(
        name.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def _send(name: str, data: bytes, inline: bool) -> Response:
    safe = name.replace('"', "").replace("\n", " ")
    return Response(content=data, media_type=_media(name),
                    headers={"Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{safe}"'})


@router.post("/tenders/{tid}/read")
async def mark_read(tid: str, read: bool = True, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    """Mark a tender read (read=true) or back to unread (read=false) for the current user."""
    uid = _user(token)
    if not uid:
        raise HTTPException(401, "Not signed in")
    await db.execute(text(
        "INSERT INTO tt_tender_reads (user_id, tid, read_at) VALUES (:uid, :tid, CASE WHEN :r THEN now() END) "
        "ON CONFLICT (user_id, tid) DO UPDATE SET read_at = CASE WHEN :r THEN now() END"), {"uid": uid, "tid": tid, "r": read})
    await db.commit()
    return {"tid": tid, "seen": "read" if read else "viewed"}


@router.get("/files/{file_id}/download")
async def download_file(file_id: str, inline: bool = False, db: AsyncSession = Depends(get_db)):
    """`inline=true` is what the viewer uses: the same bytes, shown instead of saved."""
    f = await _file(db, file_id)
    return _send(f["file_name"], bytes(f["content"]), inline)


@router.get("/files/{file_id}/text")
async def file_text(file_id: str, db: AsyncSession = Depends(get_db)):
    """Readable text of a DOCX/TXT/PDF file (for the viewer when the browser cannot show the file itself)."""
    f = await _file(db, file_id)
    name = f["file_name"]
    if os.path.splitext(name)[1].lower() not in _ANALYSABLE:
        raise HTTPException(400, "This file type cannot be shown as text.")
    parsed = await get_parser(name).parse(bytes(f["content"]), name)
    body = parsed.text or ""
    return {"file_name": name, "pages": getattr(parsed, "page_count", None), "characters": len(body),
            "truncated": len(body) > _MAX_TEXT, "text": body[:_MAX_TEXT]}


def _zip_entries(data: bytes) -> List[zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return [i for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        raise HTTPException(400, "This zip file is damaged.")


@router.get("/files/{file_id}/zip")
async def zip_contents(file_id: str, db: AsyncSession = Depends(get_db)):
    f = await _file(db, file_id)
    entries = _zip_entries(bytes(f["content"]))
    return [{"index": n, "name": i.filename, "size": i.file_size,
             "viewable": os.path.splitext(i.filename)[1].lower() in _ANALYSABLE} for n, i in enumerate(entries)]


@router.get("/files/{file_id}/zip/{index}")
async def zip_entry(file_id: str, index: int, inline: bool = False, db: AsyncSession = Depends(get_db)):
    """One file from inside a stored zip. Read in memory by position only: nothing is extracted to disk."""
    f = await _file(db, file_id)
    data = bytes(f["content"])
    entries = _zip_entries(data)
    if not 0 <= index < len(entries):
        raise HTTPException(404, "File not found in the zip")
    info = entries[index]
    if info.file_size > _MAX_ZIP_ENTRY:
        raise HTTPException(400, "This file is too large to open from the zip.")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        content = z.read(info)
    return _send(os.path.basename(info.filename) or "file", content, inline)


@router.post("/files/{file_id}/analyse", status_code=202)
async def analyse_file(file_id: str, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    """Run the eligibility analysis on a stored tender file, exactly as if it had been uploaded."""
    f = await _file(db, file_id)
    ext = os.path.splitext(f["file_name"])[1].lower()
    if ext not in _ANALYSABLE or f["kind"] == "zip":
        raise HTTPException(400, "Only a PDF, DOCX or TXT file can be analysed. Download the zip and upload the file inside it.")
    data = bytes(f["content"])
    if len(data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.")
    options = RunOptions.build()
    await check_model_available(options)
    if ext == ".pdf":
        try:
            await asyncio.to_thread(FileValidator.validate_file, f["file_name"], data)
        except FileValidationError as e:
            raise HTTPException(400, e.message)

    path = await file_store.save(["tenders"], f["file_name"], data)
    doc = Document(filename=os.path.basename(path), original_filename=f["file_name"], file_path=path,
                   doc_type=DocumentType.TENDER, status=DocumentStatus.ANALYZED,
                   uploaded_by=int(decode_token(token).get("sub", 1)))
    db.add(doc)
    await db.flush()
    await db.commit()
    report = await start_run(db, doc, options)
    return {"run_id": str(report.id), "filename": f["file_name"], "status": "pending", "model": options.resolved_model()}


# ── Automatic analysis (n8n calls this after each download) ─────────────────────────────────────────────────────────────
class _AutoBody(BaseModel):
    tids: List[str]


@router.post("/auto-analyse")
async def auto_analyse(body: _AutoBody, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    """Queue downloaded tenders for automatic analysis; answers at once (the analyses run one by one in the background)."""
    from app.services.tender_tiger.auto_queue import enqueue
    if not settings.AUTO_ANALYSE:
        raise HTTPException(409, "Automatic analysis is switched off (Settings > Tender Analysis).")
    return await enqueue(db, body.tids[:500], _user(token) or None)


@router.get("/queue")
async def auto_queue_status(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT q.tid, q.status, q.priority, q.attempts, q.reason, q.stage, q.verdict, q.report_id, q.documents, "
        "q.teams_sent_at, q.teams_error, q.created_at, q.started_at, q.finished_at, t.tender_title, t.organization, t.due_date "
        "FROM tt_analysis_queue q LEFT JOIN tt_tenders t ON t.tid = q.tid "
        "ORDER BY CASE q.status WHEN 'running' THEN 0 WHEN 'waiting' THEN 1 ELSE 2 END, "
        "q.priority DESC, COALESCE(q.finished_at, q.created_at) DESC LIMIT 100"))).mappings().all()
    counts = dict((await db.execute(text("SELECT status, count(*) FROM tt_analysis_queue GROUP BY status"))).all())
    out = []
    for r in rows:
        d = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
        d["report_id"] = str(r["report_id"]) if r["report_id"] else None
        out.append(d)
    return {"enabled": bool(settings.AUTO_ANALYSE), "counts": counts, "items": out}


@router.post("/queue/{tid}/retry")
async def auto_queue_retry(tid: str, db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    """'Analyse again': re-queue a tender first in line, without the time limit."""
    from app.services.tender_tiger.auto_queue import requeue
    if not (await db.execute(text("SELECT 1 FROM tt_tenders WHERE tid = :tid"), {"tid": tid})).first():
        raise HTTPException(404, "Tender not found")
    if not await requeue(db, tid, _user(token) or None):
        raise HTTPException(409, "This tender is being analysed right now.")
    return {"tid": tid, "status": "waiting"}
