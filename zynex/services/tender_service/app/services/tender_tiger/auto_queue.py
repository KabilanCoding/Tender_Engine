"""Automatic analysis of downloaded Tender Tiger tenders, one at a time, with a Microsoft Teams card after each one.

n8n calls POST /api/v1/tender-tiger/auto-analyse with the TIDs it downloaded; `enqueue` adds them to tt_analysis_queue
and `worker_forever` (started with the app) works through the queue:

    pick the documents (doc_picker) -> join them into one PDF -> the normal eligibility run (start_run)
    -> wait at most AUTO_TIMEOUT_MIN minutes, else stop it -> save the outcome -> Teams card

Runs survive a restart (a "running" row goes back to "waiting"). A failed run is retried once; a stopped one is not
("Analyse again" in ZYNEX re-queues it without the time limit). When the queue empties, one run-summary card is sent.
"""
import asyncio
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.core import file_store
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.tender_tiger import doc_picker, teams_notify

logger = logging.getLogger(__name__)

MANUAL = 2          # priority of an "Analyse again" request: first in line and no time limit
URGENT = 1          # closes within 3 days
_finished: List[Dict[str, Any]] = []     # outcomes since the last run-summary card


async def enqueue(db, tids: List[str], user_id: Optional[int]) -> Dict[str, Any]:
    """Queue new TIDs. Already queued or analysed tenders are not added again; closed ones are skipped when set."""
    out = {"queued": [], "skipped_closed": [], "already": [], "unknown": [], "queue_full": []}
    waiting = (await db.execute(text("SELECT count(*) FROM tt_analysis_queue WHERE status IN ('waiting','running')"))).scalar()
    today = date.today()
    for tid in dict.fromkeys(str(t).strip() for t in tids if str(t).strip()):
        t = (await db.execute(text("SELECT tid, due_date FROM tt_tenders WHERE tid = :tid"), {"tid": tid})).mappings().first()
        if t is None:
            out["unknown"].append(tid)
            continue
        if (await db.execute(text("SELECT 1 FROM tt_analysis_queue WHERE tid = :tid"), {"tid": tid})).first():
            out["already"].append(tid)
            continue
        due = t["due_date"]
        if settings.AUTO_SKIP_CLOSED and due and due < today:
            await db.execute(text("INSERT INTO tt_analysis_queue (tid, status, reason, created_by, finished_at) "
                                  "VALUES (:tid, 'skipped', 'closed: the due date has passed', :uid, now())"),
                             {"tid": tid, "uid": user_id})
            out["skipped_closed"].append(tid)
            continue
        if waiting >= settings.AUTO_QUEUE_MAX:
            out["queue_full"].append(tid)
            continue
        prio = URGENT if due and due <= today + timedelta(days=3) else 0
        await db.execute(text("INSERT INTO tt_analysis_queue (tid, priority, created_by) VALUES (:tid, :p, :uid)"),
                         {"tid": tid, "p": prio, "uid": user_id})
        waiting += 1
        out["queued"].append(tid)
    await db.commit()
    return {**{k: len(v) for k, v in out.items()}, "tids": out}


async def requeue(db, tid: str, user_id: Optional[int]) -> bool:
    """'Analyse again': back in the queue, first in line, without the time limit."""
    r = await db.execute(text(
        "INSERT INTO tt_analysis_queue (tid, priority, created_by) VALUES (:tid, :p, :uid) "
        "ON CONFLICT (tid) DO UPDATE SET status = 'waiting', priority = :p, attempts = 0, reason = NULL, stage = NULL, "
        "teams_sent_at = NULL, teams_error = NULL, started_at = NULL, finished_at = NULL "
        "WHERE tt_analysis_queue.status <> 'running' RETURNING id"), {"tid": tid, "p": MANUAL, "uid": user_id})
    await db.commit()
    return r.first() is not None


async def worker_forever() -> None:
    """Started once with the app. Assumes one server process (as in the systemd unit)."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("UPDATE tt_analysis_queue SET status = 'waiting', stage = NULL WHERE status = 'running'"))
            await db.commit()
    except Exception as e:                    # table missing until the migration runs
        logger.warning("Auto-analysis queue not available (%s); run the migrations.", e)
        return
    while True:
        try:
            if settings.AUTO_ANALYSE and await _next():
                continue                       # straight on to the next tender
            if _finished:
                await _summary()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Auto-analysis worker error")
        await asyncio.sleep(15)


async def _next() -> bool:
    async with AsyncSessionLocal() as db:
        job = (await db.execute(text(
            "UPDATE tt_analysis_queue SET status = 'running', started_at = now(), attempts = attempts + 1, stage = NULL "
            "WHERE id = (SELECT id FROM tt_analysis_queue WHERE status = 'waiting' "
            "ORDER BY priority DESC, created_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *"))).mappings().first()
        await db.commit()
    if job is None:
        return False
    await _process(dict(job))
    return True


async def _save(job_id: int, **cols) -> None:
    import json
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    vals = {k: (json.dumps(v, default=str) if k == "documents" else v) for k, v in cols.items()}
    async with AsyncSessionLocal() as db:
        await db.execute(text(f"UPDATE tt_analysis_queue SET {sets} WHERE id = :id".replace(
            ":documents", "CAST(:documents AS jsonb)")), {**vals, "id": job_id})
        await db.commit()


async def _process(job: Dict[str, Any]) -> None:
    from app.ai.tender.run_options import RunOptions
    from app.api.v1 import eligibility, progress_store
    from app.api.v1.tender_tiger import _file, _tender_files
    from app.models.document import Document, DocumentStatus, DocumentType
    from app.models.tender import EligibilityReport

    tid, started = job["tid"], time.time()
    async with AsyncSessionLocal() as db:
        tender = dict((await db.execute(text(
            "SELECT tid, tender_title, organization, due_date FROM tt_tenders WHERE tid = :tid"), {"tid": tid})).mappings().first() or {"tid": tid})

        # 1. the tender's files, and which of them to analyse
        files = []
        for f in await _tender_files(db, tid):
            if f["kind"] == "zip":
                continue
            entry = {"file_name": f["file_name"], "content": b""}
            if os.path.splitext(f["file_name"])[1].lower() in (".pdf", ".docx", ".txt"):
                try:
                    entry["content"] = bytes((await _file(db, f["id"]))["content"])
                except Exception as e:
                    logger.warning("TID %s: could not read %s (%s)", tid, f["file_name"], e)
            files.append(entry)
        picked = doc_picker.pick(files)
        docs = {"analyse": [{k: a[k] for k in ("name", "role", "pages", "score", "reason")} for a in picked["analyse"]],
                "skipped": picked["skipped"], "guessed": picked["guessed"]}
        if not picked["analyse"]:
            job.update(status="no_documents", documents=docs,
                       reason="no tender document found among the downloaded files; check them by hand" if files
                       else "no files were downloaded for this tender")
            await _save(job["id"], status=job["status"], documents=docs, reason=job["reason"], finished_at=datetime.now(timezone.utc))
            return await _report(job, tender, None, started)

        # 2. one PDF for the normal eligibility run
        try:
            combined, page_map = await asyncio.to_thread(doc_picker.combine, picked["analyse"])
        except Exception as e:
            job.update(status="failed", reason=f"could not join the documents: {e}", documents=docs)
            await _save(job["id"], status="failed", reason=job["reason"], documents=docs, finished_at=datetime.now(timezone.utc))
            return await _report(job, tender, None, started)
        docs["page_map"] = page_map
        title = "".join(ch if ch.isalnum() or ch in " -_" else " " for ch in (tender.get("tender_title") or ""))[:60].strip()
        name = f"TT_{tid}_{title or 'tender'}.pdf".replace(" ", "_")
        path = await file_store.save(["tenders"], name, combined)
        owner = job.get("created_by") or (await db.execute(text(
            "SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id WHERE r.name = 'admin' ORDER BY u.id LIMIT 1"))).scalar()
        doc = Document(filename=os.path.basename(path), original_filename=name, file_path=path,
                       doc_type=DocumentType.TENDER, status=DocumentStatus.ANALYZED, uploaded_by=owner)
        db.add(doc)
        await db.commit()
        report = await eligibility.start_run(db, doc, RunOptions.build())
        job.update(document_id=doc.id, report_id=report.id, documents=docs)
        await _save(job["id"], document_id=doc.id, report_id=report.id, documents=docs)

        # 3. wait for it, at most AUTO_TIMEOUT_MIN minutes (no limit for "Analyse again")
        task = eligibility._TASKS.get(report.id)
        limit = None if job["priority"] == MANUAL else max(1, int(settings.AUTO_TIMEOUT_MIN)) * 60
        stopped = False
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=limit)
            except asyncio.TimeoutError:
                job["stage"] = progress_store.get_stage(eligibility._elig_key(doc.id))
                await eligibility.stop_run(db, report)
                stopped = True
        report = (await db.execute(text("SELECT id, status::text AS status, compliance_matrix, criteria, summary "
                                        "FROM eligibility_reports WHERE id = :id"), {"id": report.id})).mappings().first()
        report = dict(report) if report else None
        rep = await db.get(EligibilityReport, job["report_id"])
        if rep is not None:                  # the report remembers which file each joined page came from
            rep.compliance_matrix = {**(rep.compliance_matrix or {}), "tt_documents": docs}
            await db.commit()

    state = ((report or {}).get("compliance_matrix") or {}).get("state")
    if stopped:
        job.update(status="stopped", reason=f"took longer than {settings.AUTO_TIMEOUT_MIN} minutes "
                                            f"({len(docs['analyse'])} document(s), {sum(a['pages'] for a in docs['analyse'])} pages)")
    elif state == "DONE":
        job.update(status="done", verdict=report["status"], reason=None)
    else:
        err = ((report or {}).get("compliance_matrix") or {}).get("error") or (report or {}).get("summary") or "the analysis did not finish"
        if job["attempts"] < 2:            # one automatic retry, without a card
            await _save(job["id"], status="waiting", reason=f"retrying after: {err}")
            return
        job.update(status="failed", reason=err)
    job["stage"] = job.get("stage") or None
    await _save(job["id"], status=job["status"], verdict=job.get("verdict"), reason=job.get("reason"), stage=job["stage"],
                finished_at=datetime.now(timezone.utc))
    await _report(job, tender, report, started)


async def _report(job: Dict[str, Any], tender: Dict[str, Any], report: Optional[Dict[str, Any]], started: float) -> None:
    minutes = (time.time() - started) / 60
    error = await teams_notify.send(teams_notify.card(tender, job, report, minutes))
    await _save(job["id"], teams_sent_at=None if error else datetime.now(timezone.utc), teams_error=error)
    _finished.append({"status": job["status"], "verdict": job.get("verdict")})


async def _summary() -> None:
    """One card when the queue is empty again: how this batch went."""
    async with AsyncSessionLocal() as db:
        left = (await db.execute(text("SELECT count(*) FROM tt_analysis_queue WHERE status IN ('waiting','running')"))).scalar()
    if left:
        return
    done = list(_finished)
    _finished.clear()
    count = lambda pred: sum(1 for d in done if pred(d))
    parts = [f"{count(lambda d: d['status'] == 'done')} analysed",
             f"✅ {count(lambda d: d['verdict'] == 'ELIGIBLE')} eligible",
             f"⚠️ {count(lambda d: d['verdict'] in ('PARTIAL', 'PENDING'))} partial / cannot confirm",
             f"❌ {count(lambda d: d['verdict'] == 'NOT_ELIGIBLE')} not eligible"]
    other = count(lambda d: d["status"] in ("stopped", "failed", "no_documents"))
    if other:
        parts.append(f"🛑 {other} stopped / failed / no documents")
    await teams_notify.send("<p>📊 <b>ZYNEX tender analysis · run complete</b></p><p>" + " · ".join(parts) + "</p>")
