import asyncio
import functools
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tender.amendments import extract_amendments
from app.ai.tender.checklist import extract_checklist
from app.ai.tender.criteria_extractor import CriteriaExtractor
from app.ai import cloud_clients
from app.ai.llm_client import llm_client
from app.ai.tender.reasoner import ReasoningGenerator
from app.ai.tender.run_options import RunOptions
from app.api.v1 import progress_store
from app.api.v1.progress_store import get as progress_get
from app.core import file_store
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import require_role
from app.models.document import Document, DocumentStatus
from app.models.tender import EligibilityReport, EligibilityStatus
from app.parsers.parser_factory import get_parser
from app.services.eligibility.company_facts import CompanyFactsProvider
from app.services.kb_index import semantic_matches
from app.services.eligibility.errors import EligibilityError
from app.services.eligibility.pipeline import EligibilityPipeline
from app.services.eligibility.report_shape import to_report_rows
from app.services.eligibility.verdict import action_checklist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eligibility", tags=["eligibility"])

# live analysis tasks by report id, so a run can be stopped (and so Python keeps a reference to them)
_TASKS: Dict[int, "asyncio.Task[None]"] = {}


def _elig_key(doc_id: int) -> str:
    return f"elig_{doc_id}"


class EligibilityResponse(BaseModel):
    id: int
    document_id: int
    status: str
    criteria: Optional[dict] = None
    compliance_matrix: Optional[dict] = None
    missing_documents: Optional[list] = None
    summary: Optional[str] = None

    class Config:
        from_attributes = True


async def latest_report(db: AsyncSession, doc_id: int) -> Optional[EligibilityReport]:
    result = await db.execute(
        select(EligibilityReport)
        .where(EligibilityReport.document_id == doc_id)
        .order_by(EligibilityReport.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


class RunBody(BaseModel):
    """Optional per-run LLM options (the Settings page sends these)."""
    model: Optional[str] = None
    num_ctx: Optional[int] = None
    max_tokens: Optional[int] = None
    instructions: Optional[str] = None


def run_info(options: RunOptions) -> dict:
    """What this run was configured with, stored on the report so it is auditable."""
    return {**options.to_dict(), "model": options.resolved_model(), "model_source": options.source(),
            "num_ctx": options.resolved_num_ctx(), "provider": cloud_clients.effective_provider()}


async def check_model_available(options: RunOptions) -> None:
    """Fail at submit time (HTTP 400) instead of mid-run when the chosen model or cloud service is not usable."""
    provider = cloud_clients.effective_provider()
    if provider in cloud_clients.CLOUD_PROVIDERS:
        cfg = cloud_clients.settings_for(provider)
        problems = cloud_clients.problems_with(provider, cfg["url"], cfg["key"], cfg["model"])
        if problems:
            raise HTTPException(400, "; ".join(problems) + ". An administrator must fix it under Settings > Tender Analysis.")
        return
    if not options.resolved_model() and provider == "ollama":
        raise HTTPException(400, "No AI model is selected. An administrator must choose a default model "
                                 "under Settings > AI Model before tenders can be analysed.")
    if not options.model:
        return
    available = await llm_client.list_models()
    if available and options.model not in available:
        raise HTTPException(400, f"Model '{options.model}' is not available on the {provider} server. "
                                 f"Pick an installed model in Settings (installed: {', '.join(available)}).")


async def _run_pipeline(report_id: int, doc_id: int, options_dict: Optional[dict] = None) -> None:
    """Background job: runs the pipeline with its own DB session and saves the outcome."""
    from app.core.database import AsyncSessionLocal

    key = _elig_key(doc_id)
    options = RunOptions.from_dict(options_dict)

    def say(message: str, level: str = "info", stage: Optional[str] = None, metrics: Optional[dict] = None) -> None:
        progress_store.push(key, message, level)
        if stage:
            progress_store.set_stage(key, stage)
        if metrics:
            progress_store.update_metrics(key, **metrics)

    async with AsyncSessionLocal() as db:
        report = (await db.execute(select(EligibilityReport).where(EligibilityReport.id == report_id))).scalar_one()
        try:
            doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            file_bytes = None
            if doc.file_path:
                try:
                    file_bytes = await file_store.read(doc.file_path)
                except file_store.StorageError as e:
                    say(f"Could not open the stored file: {e}", "warning")

            is_pdf = doc.original_filename.lower().endswith(".pdf")
            if not is_pdf and not doc.extracted_text and file_bytes:
                say("Extracting text from document…", "working")
                parsed = await get_parser(doc.original_filename).parse(file_bytes, doc.original_filename)
                doc.extracted_text, doc.page_count = parsed.text, parsed.page_count
                await db.commit()

            from app.services.eligibility import trace
            tr = trace.start(report_id, doc.original_filename)
            if tr:
                say(f"Trace folder: {tr.path}", "info")
            say("Loading company knowledge base…", "working")
            facts = await CompanyFactsProvider.load(db)

            progress_store.update_metrics(key, llm_model=options.resolved_model(),
                concurrency=settings.LLM_CONCURRENCY, grounding_threshold=settings.GROUNDING_FUZZY_THRESHOLD)
            say(f"AI model: {options.resolved_model()} ({options.source()})", "info")
            pipeline = EligibilityPipeline(
                extractor=CriteriaExtractor(options),
                explain=functools.partial(ReasoningGenerator.explain, options=options),
                progress=say,
                amend=functools.partial(extract_amendments, options=options),
                semantic=functools.partial(semantic_matches, db, options=options),
                checklist=functools.partial(extract_checklist, options=options) if settings.FULL_CHECKLIST else None,
            )
            out = await pipeline.run(
                run_id=uuid.uuid4().hex, filename=doc.original_filename,
                file_bytes=file_bytes, text=doc.extracted_text, facts=facts,
            )

            verdict = out["verdict"]
            report.status = EligibilityStatus(verdict["status"])
            report.criteria = {"criteria": to_report_rows(out["results"])}
            report.missing_documents = verdict["missing_documents"]
            report.summary = verdict["summary"]
            report.compliance_matrix = {
                "state": "DONE", "counts": verdict["counts"], "metrics": out["metrics"],
                "document_type": verdict.get("document_type", "tender"),
                "provider": cloud_clients.effective_provider(), "stages": out["stages"], "run": run_info(options),
                "action_checklist": action_checklist(out["results"]),
                "checklist": out.get("checklist"),
                "groups": verdict.get("groups"), "best_group": verdict.get("best_group"),
                "key_dates": verdict.get("key_dates"), "deadline_warning": verdict.get("deadline_warning"),
            }
            say(f"Result: {verdict['status']}. {verdict['summary']}", "info")
            say("Analysis complete!", "success", stage="DONE")
        except asyncio.CancelledError:
            # the user pressed Stop: cancelling the task also closes any in-flight request to the model,
            # which makes Ollama stop generating. Record it and finish normally.
            report.compliance_matrix = {"state": "CANCELLED", "run": run_info(options)}
            report.summary = "Analysis stopped by the user."
            say("Analysis stopped by the user.", "info", stage="CANCELLED")
        except EligibilityError as e:
            report.compliance_matrix = {"state": "FAILED", "error": e.message, "run": run_info(options)}
            report.summary = e.message
            say(e.message, "error")
        except Exception as e:  # keep the failure visible in the UI instead of a silent hang
            logger.exception("[Eligibility] doc_id=%s failed", doc_id)
            report.compliance_matrix = {"state": "FAILED", "error": f"{type(e).__name__}: {e}", "run": run_info(options)}
            report.summary = f"Analysis failed: {e}"
            say(f"Analysis failed: {e}", "error")
        finally:
            await db.commit()


async def fail_interrupted_runs(db: AsyncSession) -> int:
    """Called once at start-up. A run still marked RUNNING cannot be alive: its worker task died with the previous
    server process, so mark it FAILED (the user sees why and can upload again) instead of leaving it 'processing'.
    Assumes one server process, as in the systemd unit."""
    n = 0
    for report in (await db.execute(select(EligibilityReport))).scalars():
        matrix = report.compliance_matrix or {}
        if matrix.get("state") == "RUNNING":
            report.compliance_matrix = {**matrix, "state": "FAILED", "error": "The server restarted while this analysis was running."}
            report.summary = "Analysis was interrupted because the server restarted. Upload the document again to retry."
            n += 1
    if n:
        await db.commit()
    return n


async def start_run(db: AsyncSession, doc: Document, options: Optional[RunOptions] = None) -> EligibilityReport:
    """Create a RUNNING report for `doc` (replacing older ones) and schedule the pipeline."""
    existing = await latest_report(db, doc.id)
    if existing and (existing.compliance_matrix or {}).get("state") == "RUNNING":
        started = existing.created_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started and datetime.now(timezone.utc) - started < timedelta(minutes=settings.ELIGIBILITY_RUN_TTL_MIN):
            raise HTTPException(409, "An eligibility analysis is already running for this document")

    options = options or RunOptions()
    await db.execute(delete(EligibilityReport).where(EligibilityReport.document_id == doc.id))
    report = EligibilityReport(
        document_id=doc.id, status=EligibilityStatus.PENDING, criteria=None,
        compliance_matrix={"state": "RUNNING", "run": run_info(options)}, missing_documents=[], summary="Analysis in progress…",
    )
    db.add(report)
    await db.flush()
    report_id, doc_id = report.id, doc.id
    await db.commit()

    progress_store.init(_elig_key(doc_id))
    progress_store.push(_elig_key(doc_id), "Starting eligibility analysis…", "info")
    task = asyncio.create_task(_run_pipeline(report_id, doc_id, options.to_dict()))
    _TASKS[report_id] = task
    task.add_done_callback(lambda _t, rid=report_id: _TASKS.pop(rid, None))
    return report


async def stop_run(db: AsyncSession, report: EligibilityReport) -> None:
    """Stop a running analysis. Also clears a run whose process disappeared (e.g. the server restarted)."""
    task = _TASKS.get(report.id)
    if task is not None and not task.done():
        task.cancel()
        await asyncio.wait({task}, timeout=10)      # the task records CANCELLED itself
        await db.refresh(report)
    if (report.compliance_matrix or {}).get("state") == "RUNNING":
        report.compliance_matrix = {**(report.compliance_matrix or {}), "state": "CANCELLED"}
        report.summary = "Analysis stopped by the user."
        await db.commit()


@router.post("/{doc_id}/run", response_model=EligibilityResponse, status_code=202)
async def run_eligibility(
    doc_id: int,
    body: Optional[RunBody] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_role("admin", "analyst")),
):
    options = RunOptions.build(*(body.model, body.num_ctx, body.max_tokens, body.instructions)) if body else RunOptions()
    await check_model_available(options)
    doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status != DocumentStatus.ANALYZED:
        raise HTTPException(400, "Document must be analyzed first")
    return await start_run(db, doc, options)


@router.get("/{doc_id}/progress")
async def get_eligibility_progress(
    doc_id: int,
    _user: dict = Depends(require_role("admin", "analyst", "viewer")),
):
    """Poll progress messages for eligibility analysis."""
    return {"messages": progress_get(_elig_key(doc_id))}


@router.get("/{doc_id}", response_model=EligibilityResponse)
async def get_eligibility(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_role("admin", "analyst", "viewer")),
):
    report = await latest_report(db, doc_id)
    if not report:
        raise HTTPException(404, "Eligibility report not found")
    return report
