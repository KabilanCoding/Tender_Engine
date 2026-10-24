from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import date

from app.core.dependencies import get_db
from app.services.project_category import guess_category
from app.models.knowledge_base import Client, Project, Employee, Technology, Certification, CostParameter
from app.ai.kb_assembler import KBAssembler

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ClientSchema(BaseModel):
    id: int
    name: str
    industry: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    client_code: Optional[str] = None
    client_type: Optional[str] = None
    state_region: Optional[str] = None
    engagement_status: Optional[str] = None
    class Config: from_attributes = True

class ClientCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    client_code: Optional[str] = None
    client_type: Optional[str] = None
    state_region: Optional[str] = None
    engagement_status: Optional[str] = None


class ProjectSchema(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    technologies: Optional[list] = None
    team_size: Optional[int] = None
    duration_weeks: Optional[int] = None
    total_value: Optional[float] = None
    client_id: Optional[int] = None
    project_code: Optional[str] = None
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    domain: Optional[str] = None
    order_no: Optional[str] = None
    work_order_date: Optional[date] = None
    project_role: Optional[str] = None
    evidence_files: Optional[list] = None
    portfolio_category: Optional[str] = None
    status: str
    class Config: from_attributes = True

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    technologies: Optional[list] = None
    team_size: Optional[int] = None
    duration_weeks: Optional[int] = None
    total_value: Optional[float] = None
    client_id: Optional[int] = None
    project_code: Optional[str] = None
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    domain: Optional[str] = None
    order_no: Optional[str] = None
    work_order_date: Optional[date] = None
    project_role: Optional[str] = None
    evidence_files: Optional[list] = None
    portfolio_category: Optional[str] = None
    status: str = "completed"


class EmployeeSchema(BaseModel):
    id: int
    name: str
    role: str
    level: Optional[str] = None
    skills: Optional[list] = None
    hourly_rate: Optional[float] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    experience_years: Optional[float] = None
    qualification: Optional[str] = None
    professional_certifications: Optional[str] = None
    work_mode: Optional[str] = None
    joining_date: Optional[date] = None
    is_key_personnel: Optional[bool] = None
    govt_experience_years: Optional[float] = None
    relevant_experience_years: Optional[float] = None
    is_active: bool
    class Config: from_attributes = True

class EmployeeCreate(BaseModel):
    name: str
    role: str
    level: Optional[str] = None
    skills: Optional[list] = None
    hourly_rate: Optional[float] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    experience_years: Optional[float] = None
    qualification: Optional[str] = None
    professional_certifications: Optional[str] = None
    work_mode: Optional[str] = None
    joining_date: Optional[date] = None
    is_key_personnel: Optional[bool] = None
    govt_experience_years: Optional[float] = None
    relevant_experience_years: Optional[float] = None
    is_active: bool = True


class TechnologySchema(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    proficiency: Optional[str] = None
    canonical_id: Optional[str] = None
    experience_years: Optional[float] = None
    class Config: from_attributes = True

class TechnologyCreate(BaseModel):
    name: str
    category: Optional[str] = None
    proficiency: Optional[str] = None
    canonical_id: Optional[str] = None
    experience_years: Optional[float] = None


class CertificationSchema(BaseModel):
    id: int
    name: str
    issuing_body: Optional[str] = None
    certificate_number: Optional[str] = None
    valid_until: Optional[str] = None
    cert_code: Optional[str] = None
    issued_on: Optional[date] = None
    valid_until_date: Optional[date] = None
    status: Optional[str] = None
    document_path: Optional[str] = None
    class Config: from_attributes = True

class CertificationCreate(BaseModel):
    name: str
    issuing_body: Optional[str] = None
    certificate_number: Optional[str] = None
    valid_until: Optional[str] = None
    cert_code: Optional[str] = None
    issued_on: Optional[date] = None
    valid_until_date: Optional[date] = None
    status: Optional[str] = None
    document_path: Optional[str] = None


class CostParameterSchema(BaseModel):
    id: int
    role: str
    level: str
    hourly_rate: float
    qa_percentage: float
    devops_percentage: float
    contingency_percentage: float
    profit_margin_percentage: float
    class Config: from_attributes = True

class CostParameterUpdate(BaseModel):
    hourly_rate: Optional[float] = None
    qa_percentage: Optional[float] = None
    devops_percentage: Optional[float] = None
    contingency_percentage: Optional[float] = None
    profit_margin_percentage: Optional[float] = None


# ── Clients ───────────────────────────────────────────────────────────────────

@router.get("/clients", response_model=list[ClientSchema])
async def list_clients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).order_by(Client.name))
    return result.scalars().all()

@router.post("/clients", response_model=ClientSchema, status_code=201)
async def create_client(body: ClientCreate, db: AsyncSession = Depends(get_db)):
    obj = Client(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/clients/{id}", response_model=ClientSchema)
async def update_client(id: int, body: ClientCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Client not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.delete("/clients/{id}", status_code=204)
async def delete_client(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Client not found")
    await db.delete(obj)
    await db.commit()


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[ProjectSchema])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.name))
    return result.scalars().all()

@router.post("/projects", response_model=ProjectSchema, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    if not (data.get("portfolio_category") or "").strip():     # not chosen: file it by what the project is about
        data["portfolio_category"] = guess_category(data["name"], data.get("description"), data.get("technologies"))
    obj = Project(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/projects/{id}", response_model=ProjectSchema)
async def update_project(id: int, body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Project not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.delete("/projects/{id}", status_code=204)
async def delete_project(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Project not found")
    await db.delete(obj)
    await db.commit()


# ── Employees ─────────────────────────────────────────────────────────────────

@router.get("/employees", response_model=list[EmployeeSchema])
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).order_by(Employee.name))
    return result.scalars().all()

@router.post("/employees", response_model=EmployeeSchema, status_code=201)
async def create_employee(body: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    obj = Employee(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/employees/{id}", response_model=EmployeeSchema)
async def update_employee(id: int, body: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Employee not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.delete("/employees/{id}", status_code=204)
async def delete_employee(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Employee not found")
    await db.delete(obj)
    await db.commit()


# ── Technologies ──────────────────────────────────────────────────────────────

@router.get("/technologies", response_model=list[TechnologySchema])
async def list_technologies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Technology).order_by(Technology.name))
    return result.scalars().all()

@router.post("/technologies", response_model=TechnologySchema, status_code=201)
async def create_technology(body: TechnologyCreate, db: AsyncSession = Depends(get_db)):
    obj = Technology(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/technologies/{id}", response_model=TechnologySchema)
async def update_technology(id: int, body: TechnologyCreate, db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(select(Technology).where(Technology.id == id))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Technology not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.delete("/technologies/{id}", status_code=204)
async def delete_technology(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Technology).where(Technology.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Technology not found")
    await db.delete(obj)
    await db.commit()


# ── Certifications ────────────────────────────────────────────────────────────

@router.get("/certifications", response_model=list[CertificationSchema])
async def list_certifications(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Certification).order_by(Certification.name))
    return result.scalars().all()

@router.post("/certifications", response_model=CertificationSchema, status_code=201)
async def create_certification(body: CertificationCreate, db: AsyncSession = Depends(get_db)):
    obj = Certification(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.put("/certifications/{id}", response_model=CertificationSchema)
async def update_certification(id: int, body: CertificationCreate, db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(select(Certification).where(Certification.id == id))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Certification not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.delete("/certifications/{id}", status_code=204)
async def delete_certification(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Certification).where(Certification.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Certification not found")
    await db.delete(obj)
    await db.commit()


# ── Cost Parameters ───────────────────────────────────────────────────────────

@router.get("/cost-parameters", response_model=list[CostParameterSchema])
async def list_cost_params(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CostParameter).order_by(CostParameter.role, CostParameter.level))
    return result.scalars().all()

@router.put("/cost-parameters/{id}", response_model=CostParameterSchema)
async def update_cost_param(id: int, body: CostParameterUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CostParameter).where(CostParameter.id == id))
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Cost parameter not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


# ── Semantic Search ────────────────────────────────────────────────────────────

class SearchResultSchema(BaseModel):
    id: int
    project_id: int
    chunk_text: str
    section_heading: Optional[str]
    doc_category: Optional[str]
    similarity: float


@router.get("/search", response_model=list[SearchResultSchema])
async def semantic_search(
    q: str = Query(..., min_length=2),
    top_k: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search across all indexed project document chunks."""
    assembler = KBAssembler(db)
    results = await assembler.semantic_search(q, top_k=top_k)
    return results


class SummarizeBody(BaseModel):
    query: str
    chunks: list[dict]          # list of SearchResultSchema dicts
    system_prompt: str = ""     # optional override; empty = use built-in
    temperature: float = 0.2
    model: str = ""             # empty = Ollama default


class SummarizeResponse(BaseModel):
    summary: str


@router.post("/search/summarize", response_model=SummarizeResponse)
async def summarize_search(body: SummarizeBody):
    """Pass search results to the local LLM and get a human-readable answer."""
    from app.ai.llm_client import llm_client, OllamaUnavailableError

    if not body.chunks:
        return SummarizeResponse(summary="No results to summarise.")

    # Build context block from top chunks (cap at 8 to stay within context)
    context_parts = []
    for i, ch in enumerate(body.chunks[:8], 1):
        project_id = ch.get("project_id", "?")
        heading = ch.get("section_heading") or ""
        category = (ch.get("doc_category") or "").replace("_", " ")
        text = (ch.get("chunk_text") or "").strip()
        label = f"[{i}] Project #{project_id}"
        if category:
            label += f" · {category}"
        if heading:
            label += f" — {heading}"
        context_parts.append(f"{label}\n{text}")

    context = "\n\n---\n\n".join(context_parts)

    system_instruction = body.system_prompt.strip() if body.system_prompt.strip() else (
        "You are a knowledge-base assistant for a software company.\n"
        "Answer the user's query based ONLY on the document excerpts provided.\n"
        "Group information by project when useful. Be specific: mention project IDs, "
        "technologies, or roles found in the text. Keep the answer under 200 words. "
        "Do not invent information not present in the excerpts. If nothing relevant is found, say so clearly."
    )

    prompt = f"""{system_instruction}

User query: "{body.query}"

Document excerpts:

{context}

Answer:"""

    try:
        summary = await llm_client.generate(
            prompt,
            model=body.model or None,
            temperature=body.temperature,
            max_tokens=512,
        )
        return SummarizeResponse(summary=summary.strip())
    except OllamaUnavailableError as exc:
        return SummarizeResponse(summary=f"(AI summarisation unavailable: {exc})")


# ── searchable index (RAG) ────────────────────────────────────────────────────────────────────────

@router.get("/index/status")
async def index_status(db: AsyncSession = Depends(get_db)):
    from app.services import kb_index
    return await kb_index.status(db)


@router.post("/index/rebuild")
async def index_rebuild(db: AsyncSession = Depends(get_db)):
    """Embed new or changed rows (admin only: the router allows writes for admins). Needs the embedding model on Ollama."""
    from app.services import kb_index
    return await kb_index.rebuild(db)
