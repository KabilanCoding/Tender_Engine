import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import json
import re

from app.core.dependencies import get_db
from app.models.document import Document, DocumentStatus
from app.models.estimation import EstimationReport, CostSheet
from app.ai.llm_client import llm_client
from app.ai.prompt_templates import estimation_prompt
from app.ai.kb_assembler import KBAssembler
from app.ai.tender_retriever import TenderRetriever
from app.api.v1.progress_store import init as progress_init, push as progress_push, get as progress_get

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/estimation", tags=["estimation"])


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


class EstimationResponse(BaseModel):
    id: int
    document_id: int
    modules_count: int
    total_hours: float
    total_weeks: int
    modules: Optional[dict]
    tasks: Optional[dict]

    class Config:
        from_attributes = True


class CostSheetResponse(BaseModel):
    id: int
    total_cost: float
    suggested_bid: float
    line_items: Optional[dict]

    class Config:
        from_attributes = True


@router.get("/{doc_id}/progress")
async def get_progress(doc_id: int):
    return {"messages": progress_get(doc_id)}


@router.post("/{doc_id}/run", response_model=EstimationResponse, status_code=201)
async def run_estimation(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    progress_init(doc_id)
    progress_push(doc_id, f"Loading document #{doc_id}...", "info")
    logger.info("[Estimation] doc_id=%s — started", doc_id)

    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status != DocumentStatus.ANALYZED:
        raise HTTPException(400, "Document must be analyzed before estimation")
    if not doc.extracted_text:
        raise HTTPException(400, "No text extracted from document")

    progress_push(doc_id, f"Document: {doc.original_filename} ({len(doc.extracted_text)} chars)", "success")
    logger.info("[Estimation] doc_id=%s — text extracted (%d chars)", doc_id, len(doc.extracted_text))

    # RAG: retrieve most relevant tender sections
    progress_push(doc_id, "Searching for relevant document sections (RAG)...", "working")
    logger.info("[Estimation] doc_id=%s — running TenderRetriever", doc_id)
    retriever = TenderRetriever(db)
    tender_chunks = await retriever.retrieve(
        "functional requirements modules features user stories scope",
        document_id=doc_id,
        top_k=8,
    )
    if tender_chunks:
        tender_text = "\n\n".join(
            f"[{ch.get('section_heading') or 'Section'}]\n{ch['chunk_text']}"
            for ch in tender_chunks
        )
        progress_push(doc_id, f"Retrieved {len(tender_chunks)} relevant sections", "success")
    else:
        tender_text = doc.extracted_text or ""
        progress_push(doc_id, "Using full document text (no chunks found)", "info")
    logger.info("[Estimation] doc_id=%s — %d chunks retrieved", doc_id, len(tender_chunks))

    # Assemble KB context
    progress_push(doc_id, "Assembling knowledge base context (certifications, past projects, rates)...", "working")
    logger.info("[Estimation] doc_id=%s — assembling KB context", doc_id)
    assembler = KBAssembler(db)
    kb_context = await assembler.assemble_for_estimation(tender_text[:2000])
    progress_push(
        doc_id,
        f"KB ready — {len(kb_context.certifications)} certs, {len(kb_context.past_projects)} projects, {len(kb_context.cost_parameters)} rate entries",
        "success",
    )
    logger.info("[Estimation] doc_id=%s — KB assembled", doc_id)

    # LLM generation
    progress_push(doc_id, "Sending to AI model (llama3.2) — this may take 1-3 minutes...", "working")
    logger.info("[Estimation] doc_id=%s — calling ollama generate", doc_id)
    prompt = estimation_prompt(tender_text, kb_context)
    ai_response = await llm_client.generate(prompt)
    progress_push(doc_id, f"AI response received ({len(ai_response)} chars)", "success")
    logger.info("[Estimation] doc_id=%s — AI response received (%d chars)", doc_id, len(ai_response))

    # Parse response
    progress_push(doc_id, "Parsing AI output...", "working")
    data = _extract_json(ai_response)
    if not data or "modules" not in data:
        progress_push(doc_id, "Failed to parse AI response", "error")
        logger.error("[Estimation] doc_id=%s — invalid AI format", doc_id)
        raise HTTPException(500, "AI returned invalid estimation format")

    modules = data.get("modules", [])
    sprints = data.get("sprints", [])
    progress_push(doc_id, f"Parsed: {len(modules)} modules, {len(sprints)} sprints", "success")

    # Save report
    progress_push(doc_id, "Saving estimation report...", "working")
    report = EstimationReport(
        document_id=doc_id,
        modules_count=len(modules),
        total_hours=data.get("total_hours", 0),
        total_weeks=data.get("total_weeks", 0),
        modules={"modules": modules},
        sprints={"sprints": sprints},
        tasks={"tasks": [
            task
            for sprint in sprints
            for task in sprint.get("tasks", [])
        ]},
    )
    db.add(report)
    await db.flush()

    # Build cost sheet
    tasks = report.tasks.get("tasks", [])
    dev_hours  = sum(t["hours"] for t in tasks if t.get("role") == "developer")
    qa_hours   = sum(t["hours"] for t in tasks if t.get("role") == "qa")
    dvops_hours = sum(t["hours"] for t in tasks if t.get("role") == "devops")

    def _rate(role: str, default: float) -> float:
        for p in kb_context.cost_parameters:
            if p["role"].lower() == role.lower():
                return p["hourly_rate"]
        return default

    dev_rate    = _rate("developer", 50.0)
    qa_rate     = _rate("qa", 35.0)
    devops_rate = _rate("devops", 45.0)

    dev_cost    = dev_hours * dev_rate
    qa_cost     = qa_hours * qa_rate
    devops_cost = dvops_hours * devops_rate
    infra_cost  = report.total_weeks * 200
    storage_cost = 500.0
    subtotal    = dev_cost + qa_cost + devops_cost + infra_cost + storage_cost
    contingency = subtotal * 0.10
    profit      = (subtotal + contingency) * 0.20
    total       = subtotal + contingency + profit

    cost = CostSheet(
        estimation_id=report.id,
        developer_cost=dev_cost,
        qa_cost=qa_cost,
        devops_cost=devops_cost,
        infrastructure_cost=infra_cost,
        storage_cost=storage_cost,
        contingency=contingency,
        profit_margin=profit,
        total_cost=total,
        suggested_bid=total * 1.05,
        line_items={
            "Developer": dev_cost,
            "QA": qa_cost,
            "DevOps": devops_cost,
            "Infrastructure": infra_cost,
            "Storage": storage_cost,
            "Contingency (10%)": contingency,
            "Profit Margin (20%)": profit,
        },
    )
    db.add(cost)
    await db.commit()

    progress_push(
        doc_id,
        f"Estimation complete — {report.modules_count} modules, {int(report.total_hours)}h, {report.total_weeks} weeks, total cost ${total:,.0f}",
        "success",
    )
    logger.info("[Estimation] doc_id=%s — DONE (%d modules, %.0fh, %d weeks)", doc_id, report.modules_count, report.total_hours, report.total_weeks)
    return report


@router.get("/{doc_id}", response_model=EstimationResponse)
async def get_estimation(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EstimationReport).where(EstimationReport.document_id == doc_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Estimation not found")
    return report


@router.get("/{doc_id}/cost", response_model=CostSheetResponse)
async def get_cost_sheet(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EstimationReport).where(EstimationReport.document_id == doc_id)
    )
    report = result.scalar_one_or_none()
    if not report or not report.cost_sheet:
        raise HTTPException(404, "Cost sheet not found")
    return report.cost_sheet
