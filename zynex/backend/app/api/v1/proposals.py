import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import json

from app.core import file_store
from app.core.dependencies import get_db
from app.models.document import Document
from app.models.tender import EligibilityReport, Proposal
from app.models.estimation import EstimationReport
from app.ai.llm_client import llm_client
from app.ai.prompt_templates import proposal_section_prompt
from app.exporters.docx_exporter import generate_proposal_docx
from app.exporters.pdf_exporter import generate_proposal_pdf

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalResponse(BaseModel):
    id: int
    document_id: int
    technical_proposal: Optional[str]
    commercial_proposal: Optional[str]
    sections: Optional[dict]
    docx_path: Optional[str]
    pdf_path: Optional[str]
    class Config: from_attributes = True


async def _build_proposal(proposal_id: int):
    """Background task: generate DOCX + PDF after proposal is created."""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
        proposal = result.scalar_one_or_none()
        if not proposal:
            return

        doc_result = await db.execute(select(Document).where(Document.id == proposal.document_id))
        doc = doc_result.scalar_one_or_none()

        proposal_data = {
            "title": f"Technical Proposal – {doc.original_filename if doc else 'Project'}",
            "company_name": "ZYNEX Technologies",
            "sections": proposal.sections or {},
            "technical_proposal": proposal.technical_proposal or "",
            "commercial_proposal": proposal.commercial_proposal or "",
        }

        # built in a temporary folder, then kept in the document storage (this machine or the file server)
        folder = ["proposals", str(proposal.document_id)]
        with tempfile.TemporaryDirectory() as tmp:
            try:
                built = generate_proposal_docx(proposal_data, tmp)
                with open(built, "rb") as fh:
                    proposal.docx_path = await file_store.save(folder, os.path.basename(built), fh.read())
            except Exception:
                pass

            try:
                built = generate_proposal_pdf(proposal_data, tmp)
                with open(built, "rb") as fh:
                    proposal.pdf_path = await file_store.save(folder, os.path.basename(built), fh.read())
            except Exception:
                pass

        await db.commit()


@router.post("/{doc_id}/generate", response_model=ProposalResponse, status_code=201)
async def generate_proposal(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    doc_result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    elig_result = await db.execute(
        select(EligibilityReport).where(EligibilityReport.document_id == doc_id)
    )
    eligibility = elig_result.scalar_one_or_none()

    est_result = await db.execute(
        select(EstimationReport).where(EstimationReport.document_id == doc_id)
    )
    estimation = est_result.scalar_one_or_none()

    context = {
        "company_name": "ZYNEX Technologies",
        "project_name": doc.original_filename,
        "requirements_summary": (doc.extracted_text or "")[:1000],
        "technologies": ["Python", "React", "PostgreSQL", "FastAPI"],
        "modules_count": estimation.modules_count if estimation else 0,
        "total_hours": estimation.total_hours if estimation else 0,
        "total_weeks": estimation.total_weeks if estimation else 0,
    }

    sections: dict[str, str] = {}
    section_keys = [
        "executive_summary",
        "technical_approach",
        "project_plan",
        "team_composition",
        "company_profile",
        "commercial_proposal",
        "compliance",
    ]

    for key in section_keys:
        try:
            prompt = proposal_section_prompt(key.replace("_", " ").title(), context)
            sections[key] = await llm_client.generate(prompt)
        except Exception:
            sections[key] = f"[{key.replace('_', ' ').title()} — to be completed]"

    proposal = Proposal(
        document_id=doc_id,
        eligibility_report_id=eligibility.id if eligibility else None,
        technical_proposal=sections.get("technical_approach", ""),
        commercial_proposal=sections.get("commercial_proposal", ""),
        company_profile=sections.get("company_profile", ""),
        sections=sections,
    )
    db.add(proposal)
    await db.flush()
    proposal_id = proposal.id
    await db.commit()

    background_tasks.add_task(_build_proposal, proposal_id)
    return proposal


@router.get("/", response_model=list[int])
async def documents_with_proposals(db: AsyncSession = Depends(get_db)):
    """Ids of the documents that already have a proposal, so a screen can ask for one only when it exists."""
    rows = await db.execute(select(Proposal.document_id).distinct())
    return sorted(r for (r,) in rows.all() if r is not None)


@router.get("/{doc_id}", response_model=ProposalResponse)
async def get_proposal(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Proposal).where(Proposal.document_id == doc_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    return proposal


@router.get("/{doc_id}/download/docx")
async def download_docx(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Proposal).where(Proposal.document_id == doc_id))
    proposal = result.scalar_one_or_none()
    if not proposal or not proposal.docx_path:
        raise HTTPException(404, "DOCX not ready yet — try again in a few seconds")
    return file_store.response(await file_store.read(proposal.docx_path), _download_name(proposal.docx_path),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document", inline=False)


@router.get("/{doc_id}/download/pdf")
async def download_pdf(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Proposal).where(Proposal.document_id == doc_id))
    proposal = result.scalar_one_or_none()
    if not proposal or not proposal.pdf_path:
        raise HTTPException(404, "PDF not ready yet — try again in a few seconds")
    return file_store.response(await file_store.read(proposal.pdf_path), _download_name(proposal.pdf_path),
                               "application/pdf", inline=False)


def _download_name(path: str) -> str:
    """The exporter's file name, without the random prefix the storage adds."""
    base = os.path.basename(path)
    prefix, _, rest = base.partition("_")
    return rest if len(prefix) == 12 and rest else base
