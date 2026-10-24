"""Tender evaluation API used by the tender screens (upload, live status, report, history, PDF).

A "run" is one EligibilityReport; run_id is the report id. The heavy lifting lives in
app.api.v1.eligibility (background job) and app.services.eligibility.
"""
import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import progress_store
from app.ai.tender.run_options import RunOptions
from app.api.v1.eligibility import _elig_key, check_model_available, start_run, stop_run
from app.core import file_store
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import decode_token, oauth2_scheme
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.estimation import EstimationReport
from app.models.estimation_project import EstimationProject
from app.models.project_documents import TenderChunk
from app.models.tender import EligibilityReport, Proposal
from app.services.eligibility.errors import FileValidationError
from app.services.eligibility.file_validator import FileValidator
from app.services.eligibility.report_pdf import build_report_pdf

router = APIRouter(prefix="/tender", tags=["tender"])

_ALLOWED_EXT = {".pdf", ".docx", ".txt"}
_VERDICT = {"ELIGIBLE": "PASS", "NOT_ELIGIBLE": "FAIL", "PARTIAL": "PARTIAL", "PENDING": "PARTIAL"}
_LEGACY_STATUS = {"met": "PASS", "not_met": "FAIL"}  # reports written before the staged pipeline


def _state(report: EligibilityReport) -> str:
    state = (report.compliance_matrix or {}).get("state")
    if state:
        return state
    return "DONE" if (report.criteria or {}).get("criteria") else "RUNNING"  # legacy reports have no state


def _run_of(report: EligibilityReport) -> Dict[str, Any]:
    return (report.compliance_matrix or {}).get("run") or {}


def _model_name(report: EligibilityReport) -> str:
    """The model this run actually used (stored at submit time); legacy runs fall back to server config."""
    return _run_of(report).get("model") or RunOptions().resolved_model()


async def _load(db: AsyncSession, run_id: str):
    try:
        rid = int(run_id)
    except ValueError:
        raise HTTPException(404, "Run not found")
    report = (await db.execute(select(EligibilityReport).where(EligibilityReport.id == rid))).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Run not found")
    doc = (await db.execute(select(Document).where(Document.id == report.document_id))).scalar_one_or_none()
    return report, doc


def _metrics(report: EligibilityReport, key: str) -> Dict[str, Any]:
    """Live metrics while running, stored metrics once done, in the shape the screens expect."""
    live = progress_store.get_metrics(key)
    stored = (report.compliance_matrix or {}).get("metrics") or {}
    llm, val = stored.get("llm", {}), stored.get("validation", {})
    out: Dict[str, Any] = {
        "execution_time_ms": int(stored.get("duration_s", 0) * 1000) or None,
        "chunks_processed": stored.get("chunks"),
        "total_chunks": stored.get("chunks"),
        "chunks_started": llm.get("llm_candidate_chunks"),
        "llm_candidate_chunks": llm.get("llm_candidate_chunks"),
        "chunks_successful": llm.get("chunks_successful"),
        "raw_criteria_found": val.get("raw_criteria_found"),
        "criteria_grounded": val.get("criteria_grounded"),
        "actual_llm_api_calls": llm.get("actual_llm_api_calls"),
        "successful_calls": llm.get("successful_calls"),
        "concurrency": llm.get("configured_concurrency"),
        "grounding_threshold": settings.GROUNDING_FUZZY_THRESHOLD,
        "llm_model": _model_name(report),
        "model_source": _run_of(report).get("model_source"),
        "num_ctx": _run_of(report).get("num_ctx"),
    }
    out.update(live)
    return {k: v for k, v in out.items() if v is not None}


def _build_report(report: EligibilityReport, doc: Optional[Document]) -> Dict[str, Any]:
    rows: List[dict] = (report.criteria or {}).get("criteria", [])
    results = [{
        "criterion_id": r.get("criterion_id") or f"C{i:03d}", "page_no": r.get("page_no") or 0,
        "field": r.get("field") or "other", "operator": r.get("operator"),
        "status": r.get("status") or _LEGACY_STATUS.get(r.get("company_status", ""), "NEEDS_REVIEW"),
        "tender_value": r.get("tender_value", r.get("required")), "tender_requirement": r.get("required"),
        "company_value": r.get("company_value"), "mandatory": r.get("mandatory", True),
        "source_text": r.get("source_text") or "", "reason": r.get("reasoning") or r.get("evidence"),
        "evidence": r.get("evidence"), "grounded": r.get("grounded", True), "is_document": bool(r.get("is_document", False)),
        "alt_group": r.get("alt_group"),
    } for i, r in enumerate(rows, start=1)]
    from app.services.eligibility.verdict import plain_title, requirement_text, status_text
    for r in results:                       # plain-English wording for the screen, also for runs saved before it existed
        r["title"] = plain_title(r["field"], r["source_text"], r["tender_value"])
        r["requirement"] = requirement_text(r.get("operator"), r["tender_value"], r["source_text"])
        r["status_label"] = status_text(r["status"])

    rank = {"PASS": 0, "NEEDS_REVIEW": 1, "MISSING": 2, "FAIL": 3}
    best: Dict[str, dict] = {}
    for r in results:                       # alternatives ('X or Y or Z'): only the best one counts in the totals
        g = r.get("alt_group")
        if g and (g not in best or rank.get(r["status"], 4) < rank.get(best[g]["status"], 4)):
            best[g] = r
    for r in results:
        r["alt_secondary"] = bool(r.get("alt_group")) and best[r["alt_group"]] is not r

    def count(status: str, mandatory: bool) -> int:
        # forms and declarations to hand in are counted on their own, not as facts that could not be verified
        return sum(1 for r in results if r["status"] == status and r["mandatory"] == mandatory and not r["is_document"]
                   and not r["alt_secondary"])

    meta = report.compliance_matrix or {}
    return {
        "run_id": str(report.id),
        "filename": doc.original_filename if doc else f"document-{report.document_id}",
        "verdict": _VERDICT.get(report.status.value, "PARTIAL"),
        "summary": report.summary,
        "mandatory_pass": count("PASS", True), "mandatory_fail": count("FAIL", True),
        "mandatory_missing": count("MISSING", True), "mandatory_review_required": count("NEEDS_REVIEW", True),
        "optional_pass": count("PASS", False), "optional_fail": count("FAIL", False),
        "documents_to_prepare": sum(1 for r in results if r["is_document"] and r["mandatory"] and r["status"] != "INFORMATIONAL"),
        "results": results,
        "action_checklist": meta.get("action_checklist", []),
        "full_checklist": meta.get("checklist"),
        "groups": meta.get("groups"), "best_group": meta.get("best_group"),
        "key_dates": meta.get("key_dates") or [], "deadline_warning": meta.get("deadline_warning"),
        "missing_documents": report.missing_documents or [],
        "metrics": _metrics(report, _elig_key(report.document_id)),
    }


@router.post("/upload", status_code=202)
async def upload_tender(
    file: UploadFile = File(...),
    model: Optional[str] = Form(None),          # the next four come from the Settings page
    num_ctx: Optional[int] = Form(None),
    max_tokens: Optional[int] = Form(None),
    instructions: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    options = RunOptions.build(model, num_ctx, max_tokens, instructions)
    await check_model_available(options)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext or 'unknown'}. Upload a PDF or DOCX tender.")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.")

    if ext == ".pdf":  # fail fast, before anything is stored: the same gate the pipeline uses
        try:
            await asyncio.to_thread(FileValidator.validate_file, file.filename, data)
        except FileValidationError as e:
            raise HTTPException(400, e.message)

    path = await file_store.save(["tenders"], file.filename or f"tender{ext}", data)

    doc = Document(
        filename=os.path.basename(path), original_filename=file.filename, file_path=path,
        doc_type=DocumentType.TENDER, status=DocumentStatus.ANALYZED,
        uploaded_by=int(decode_token(token).get("sub", 1)),
    )
    db.add(doc)
    await db.flush()
    await db.commit()
    report = await start_run(db, doc, options)
    return {"run_id": str(report.id), "filename": file.filename, "status": "pending",
            "model": options.resolved_model()}


@router.get("/history")
async def history(db: AsyncSession = Depends(get_db)):
    reports = (await db.execute(select(EligibilityReport).order_by(EligibilityReport.id.desc()))).scalars().all()
    docs = {d.id: d for d in (await db.execute(select(Document))).scalars()}
    status_names = {"RUNNING": "processing", "DONE": "completed", "FAILED": "failed", "CANCELLED": "cancelled"}
    items = []
    for r in reports:
        state = _state(r)
        d = docs.get(r.document_id)
        items.append({
            "run_id": str(r.id),
            "filename": d.original_filename if d else f"document-{r.document_id}",
            "status": status_names.get(state, "processing"),
            "verdict": _VERDICT.get(r.status.value) if state == "DONE" else None,
            "criteria_count": len((r.criteria or {}).get("criteria", [])),
            # requirements met / counted: lets the screens tell "partially eligible" from "cannot confirm yet"
            "met": ((r.compliance_matrix or {}).get("counts") or {}).get("pass"),
            "total": ((r.compliance_matrix or {}).get("counts") or {}).get("total"),
            "created_at": r.created_at.isoformat() if r.created_at else "",
        })
    return items


@router.get("/{run_id}/status")
async def run_status(run_id: str, db: AsyncSession = Depends(get_db)):
    report, _doc = await _load(db, run_id)
    key = _elig_key(report.document_id)
    state = _state(report)
    return {
        "run_id": run_id,
        "status": {"RUNNING": "processing", "DONE": "done", "FAILED": "failed", "CANCELLED": "cancelled"}.get(state, "processing"),
        "progress_step": "DONE" if state == "DONE" else progress_store.get_stage(key),
        "metrics": _metrics(report, key),
        "verdict": _VERDICT.get(report.status.value) if state == "DONE" else None,
        "error": (report.compliance_matrix or {}).get("error"),
        "messages": progress_store.get(key),
    }


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Stop a running analysis (the Stop button)."""
    report, _doc = await _load(db, run_id)
    if _state(report) != "RUNNING":
        raise HTTPException(409, "This analysis is not running")
    await stop_run(db, report)
    return {"run_id": run_id, "status": "cancelled" if _state(report) == "CANCELLED" else "stopping"}


@router.get("/{run_id}/report")
async def get_report(run_id: str, db: AsyncSession = Depends(get_db)):
    report, doc = await _load(db, run_id)
    if _state(report) != "DONE":
        raise HTTPException(409, "The analysis has not finished yet")
    return _build_report(report, doc)


@router.get("/{run_id}/stages")
async def get_stages(run_id: str, db: AsyncSession = Depends(get_db)):
    report, doc = await _load(db, run_id)
    return {
        "run_id": run_id,
        "filename": doc.original_filename if doc else "",
        "verdict": _VERDICT.get(report.status.value),
        "stages": (report.compliance_matrix or {}).get("stages", []),
    }


@router.get("/{run_id}/report/pdf")
async def get_report_pdf(run_id: str, db: AsyncSession = Depends(get_db)):
    report, doc = await _load(db, run_id)
    if _state(report) != "DONE":
        raise HTTPException(409, "The analysis has not finished yet")
    pdf = await asyncio.to_thread(build_report_pdf, _build_report(report, doc))
    name = os.path.splitext(doc.original_filename)[0] if doc else f"run-{run_id}"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="eligibility-report-{name}.pdf"'})


@router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a run. The uploaded document goes with it unless estimation/proposal work still uses it."""
    report, doc = await _load(db, run_id)
    if _state(report) == "RUNNING":
        started = report.created_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started and datetime.now(timezone.utc) - started < timedelta(minutes=settings.ELIGIBILITY_RUN_TTL_MIN):
            raise HTTPException(409, "This analysis is still running; wait for it to finish before deleting it")

    doc_id = report.document_id
    await db.execute(sa_delete(EligibilityReport).where(EligibilityReport.id == report.id))
    await db.flush()
    progress_store.clear(_elig_key(doc_id))

    in_use = 0
    for model in (EligibilityReport, EstimationReport, Proposal, EstimationProject):
        in_use += (await db.execute(select(func.count()).select_from(model).where(model.document_id == doc_id))).scalar_one()
    if doc and in_use == 0:
        await file_store.delete(doc.file_path)
        await db.execute(sa_delete(TenderChunk).where(TenderChunk.document_id == doc_id))
        await db.delete(doc)
    await db.commit()
