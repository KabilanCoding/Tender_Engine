"""
Project Estimation API router.

Endpoints
---------
GET    /estimation-projects/                            — list all projects
POST   /estimation-projects/                            — create new project
GET    /estimation-projects/{project_id}                — get full project
PUT    /estimation-projects/{project_id}                — update settings
DELETE /estimation-projects/{project_id}                — delete project
POST   /estimation-projects/{project_id}/generate       — AI feature generation
POST   /estimation-projects/{project_id}/recalculate    — recalculate costs
POST   /estimation-projects/{project_id}/chat-reestimate— AI chat re-estimation
POST   /estimation-projects/{project_id}/features       — add a feature row
PUT    /estimation-projects/{project_id}/features/{fid} — update feature
DELETE /estimation-projects/{project_id}/features/{fid} — delete feature
PUT    /estimation-projects/{project_id}/resources/{rid}— update resource
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import OllamaUnavailableError, llm_client
from app.api.v1.estimation_calc import DEFAULT_ROLES, calc_project, recalculate_project
from app.api.v1.progress_store import (
    clear as progress_clear,
    get as progress_get,
    init as progress_init,
    push as progress_push,
)
from app.core.database import AsyncSessionLocal
from app.core.dependencies import get_db
from app.models.document import Document, DocumentStatus
from app.models.estimation_project import (
    EstimationFeature,
    EstimationProject,
    EstimationResource,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/estimation-projects", tags=["estimation-projects"])


# ---------------------------------------------------------------------------
# GET /estimation-projects/models  — list available models for the active LLM provider
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models():
    models = await llm_client.list_models()
    return {"models": models, "provider": llm_client.provider}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    document_id: Optional[int] = None
    notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    document_id: Optional[int] = None
    complexity_pct: Optional[float] = None
    unit_testing_pct: Optional[float] = None
    rework_pct: Optional[float] = None
    pm_pct: Optional[float] = None
    design_arch_pct: Optional[float] = None
    spec_uiux_pct: Optional[float] = None
    dev_buffer_pct: Optional[float] = None
    margin_pct: Optional[float] = None
    infra_cost: Optional[float] = None


class FeatureCreate(BaseModel):
    sort_order: int = 0
    milestone: Optional[str] = None
    module: Optional[str] = None
    sub_module: Optional[str] = None
    feature: str
    data_model_complexity: Optional[str] = None
    api_complexity: Optional[str] = None
    business_rules_complexity: Optional[str] = None
    ui_complexity: Optional[str] = None
    fixed_hours: float = 0.0


class FeatureUpdate(BaseModel):
    sort_order: Optional[int] = None
    milestone: Optional[str] = None
    module: Optional[str] = None
    sub_module: Optional[str] = None
    feature: Optional[str] = None
    data_model_complexity: Optional[str] = None
    api_complexity: Optional[str] = None
    business_rules_complexity: Optional[str] = None
    ui_complexity: Optional[str] = None
    fixed_hours: Optional[float] = None


class ResourceUpdate(BaseModel):
    count: Optional[int] = None
    hourly_rate: Optional[float] = None
    effort_pct: Optional[float] = None
    responsibility: Optional[str] = None
    is_active: Optional[bool] = None


class ResourceCreate(BaseModel):
    role: str
    responsibility: Optional[str] = None
    count: int = 1
    effort_pct: float = 0.05
    hourly_rate: float = 0.0


class GenerateBody(BaseModel):
    platform: Optional[str] = None          # "web" | "mobile" | "both"
    tech_stack: Optional[dict] = None       # {"frontend": ["React"], "backend": ["FastAPI"], ...}
    model: Optional[str] = None             # e.g. "llama3.2:latest" — overrides server default
    temperature: Optional[float] = None     # 0.0 = deterministic, 0.7 = creative
    seed: Optional[int] = None              # fixed seed for reproducible output


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _project_list_item(p: EstimationProject) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "status": p.status,
        "total_project_cost": p.total_project_cost,
        "grand_total_hours": p.grand_total_hours,
        "created_at": p.created_at.isoformat(),
        "document_id": p.document_id,
    }


def _feature_dict(f: EstimationFeature) -> dict:
    return {
        "id": f.id,
        "project_id": f.project_id,
        "sort_order": f.sort_order,
        "milestone": f.milestone,
        "module": f.module,
        "sub_module": f.sub_module,
        "feature": f.feature,
        "data_model_complexity": f.data_model_complexity,
        "api_complexity": f.api_complexity,
        "business_rules_complexity": f.business_rules_complexity,
        "ui_complexity": f.ui_complexity,
        "fixed_hours": f.fixed_hours,
        "base_hours": f.base_hours,
        "total_dev_hours": f.total_dev_hours,
        "total_qa_hours": f.total_qa_hours,
        "total_hours": f.total_hours,
    }


def _resource_dict(r: EstimationResource) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "sort_order": r.sort_order,
        "role": r.role,
        "responsibility": r.responsibility,
        "count": r.count,
        "effort_pct": r.effort_pct,
        "effort_hours": r.effort_hours,
        "hourly_rate": r.hourly_rate,
        "total_cost": r.total_cost,
        "is_active": getattr(r, 'is_active', True),
    }


def _project_full(p: EstimationProject, summary: dict | None = None) -> dict:
    data = {
        "id": p.id,
        "name": p.name,
        "status": p.status,
        "notes": p.notes,
        "document_id": p.document_id,
        "complexity_pct": p.complexity_pct,
        "unit_testing_pct": p.unit_testing_pct,
        "rework_pct": p.rework_pct,
        "pm_pct": p.pm_pct,
        "design_arch_pct": p.design_arch_pct,
        "spec_uiux_pct": p.spec_uiux_pct,
        "dev_buffer_pct": p.dev_buffer_pct,
        "margin_pct": p.margin_pct,
        "infra_cost": p.infra_cost,
        "total_dev_hours": p.total_dev_hours,
        "total_qa_hours": p.total_qa_hours,
        "grand_total_hours": p.grand_total_hours,
        "internal_cost": p.internal_cost,
        "margin_amount": p.margin_amount,
        "total_project_cost": p.total_project_cost,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
        "features": [_feature_dict(f) for f in p.features],
        "resources": sorted([_resource_dict(r) for r in p.resources], key=lambda x: x["sort_order"]),
    }
    if summary:
        data["summary"] = {
            "pm_hours": summary["pm_hours"],
            "design_arch_hours": summary["design_arch_hours"],
            "spec_uiux_hours": summary["spec_uiux_hours"],
            "dev_buffer_hours": summary["dev_buffer_hours"],
            "grand_total_dev": summary["grand_total_dev"],
        }
    return data


# ---------------------------------------------------------------------------
# JSON extraction helper (duplicated to keep this module self-contained)
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    # Direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"features": parsed}
    except json.JSONDecodeError:
        pass
    # Find outermost {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    # Find [...] array at top level
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            arr = json.loads(text[start:end + 1])
            if isinstance(arr, list):
                return {"features": arr}
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# Helper: create default resources for a new project
# ---------------------------------------------------------------------------

def _create_default_resources(project_id: int) -> list[EstimationResource]:
    resources: list[EstimationResource] = []
    for role_def in DEFAULT_ROLES:
        res = EstimationResource(
            project_id=project_id,
            sort_order=role_def["sort_order"],
            role=role_def["role"],
            responsibility=role_def["responsibility"],
            count=role_def["count"],
            effort_pct=role_def["effort_pct"],
            hourly_rate=role_def["hourly_rate"],
            effort_hours=0.0,
            total_cost=0.0,
        )
        resources.append(res)
    return resources


# ---------------------------------------------------------------------------
# GET /estimation-projects/
# ---------------------------------------------------------------------------

@router.get("/")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EstimationProject).order_by(EstimationProject.id.desc())
    )
    projects = result.scalars().all()
    return [_project_list_item(p) for p in projects]


# ---------------------------------------------------------------------------
# POST /estimation-projects/
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = EstimationProject(
        name=body.name,
        document_id=body.document_id,
        notes=body.notes,
        status="draft",
    )
    db.add(project)
    await db.flush()  # get project.id

    # Create default resource rows
    for res in _create_default_resources(project.id):
        db.add(res)

    await db.commit()
    await db.refresh(project)
    return _project_full(project)


# ---------------------------------------------------------------------------
# GET /estimation-projects/{project_id}
# ---------------------------------------------------------------------------

@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")

    summary = calc_project(project) if project.features else None
    return _project_full(project, summary)


# ---------------------------------------------------------------------------
# PUT /estimation-projects/{project_id}
# ---------------------------------------------------------------------------

@router.put("/{project_id}")
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    summary = calc_project(project) if project.features else None
    return _project_full(project, summary)


# ---------------------------------------------------------------------------
# DELETE /estimation-projects/{project_id}
# ---------------------------------------------------------------------------

@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")
    await db.delete(project)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /estimation-projects/{project_id}/recalculate
# ---------------------------------------------------------------------------

@router.post("/{project_id}/recalculate")
async def recalculate(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")

    recalculate_project(project)
    await db.commit()
    await db.refresh(project)
    summary = calc_project(project) if project.features else None
    return _project_full(project, summary)


# ---------------------------------------------------------------------------
# POST /estimation-projects/{project_id}/features
# ---------------------------------------------------------------------------

@router.post("/{project_id}/features", status_code=201)
async def add_feature(
    project_id: int,
    body: FeatureCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")

    feature = EstimationFeature(
        project_id=project_id,
        sort_order=body.sort_order,
        milestone=body.milestone,
        module=body.module,
        sub_module=body.sub_module,
        feature=body.feature,
        data_model_complexity=body.data_model_complexity,
        api_complexity=body.api_complexity,
        business_rules_complexity=body.business_rules_complexity,
        ui_complexity=body.ui_complexity,
        fixed_hours=body.fixed_hours,
    )
    db.add(feature)
    await db.flush()

    # Refresh project relationships then recalculate
    await db.refresh(project)
    recalculate_project(project)
    await db.commit()
    await db.refresh(project)
    summary = calc_project(project)
    return _project_full(project, summary)


# ---------------------------------------------------------------------------
# PUT /estimation-projects/{project_id}/features/{feature_id}
# ---------------------------------------------------------------------------

@router.put("/{project_id}/features/{feature_id}")
async def update_feature(
    project_id: int,
    feature_id: int,
    body: FeatureUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationFeature).where(
            EstimationFeature.id == feature_id,
            EstimationFeature.project_id == project_id,
        )
    )
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(404, "Feature not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(feature, field, value)

    await db.flush()

    # Load project and recalculate
    proj_result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = proj_result.scalar_one_or_none()
    if project:
        await db.refresh(project)
        recalculate_project(project)

    await db.commit()
    if project:
        await db.refresh(project)
        summary = calc_project(project)
        return _project_full(project, summary)
    return _feature_dict(feature)


# ---------------------------------------------------------------------------
# DELETE /estimation-projects/{project_id}/features/{feature_id}
# ---------------------------------------------------------------------------

@router.delete("/{project_id}/features/{feature_id}", status_code=200)
async def delete_feature(
    project_id: int,
    feature_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationFeature).where(
            EstimationFeature.id == feature_id,
            EstimationFeature.project_id == project_id,
        )
    )
    feature = result.scalar_one_or_none()
    if not feature:
        raise HTTPException(404, "Feature not found")

    await db.delete(feature)
    await db.flush()

    # Reload project and recalculate
    proj_result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = proj_result.scalar_one_or_none()
    if project:
        await db.refresh(project)
        recalculate_project(project)

    await db.commit()
    if project:
        await db.refresh(project)
        summary = calc_project(project) if project.features else None
        return _project_full(project, summary)
    return {"ok": True}


# ---------------------------------------------------------------------------
# PUT /estimation-projects/{project_id}/resources/{resource_id}
# ---------------------------------------------------------------------------

@router.put("/{project_id}/resources/{resource_id}")
async def update_resource(
    project_id: int,
    resource_id: int,
    body: ResourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationResource).where(
            EstimationResource.id == resource_id,
            EstimationResource.project_id == project_id,
        )
    )
    resource = result.scalar_one_or_none()
    if not resource:
        raise HTTPException(404, "Resource not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(resource, field, value)

    await db.flush()

    # Recalculate project
    proj_result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = proj_result.scalar_one_or_none()
    if project:
        await db.refresh(project)
        recalculate_project(project)

    await db.commit()
    if project:
        await db.refresh(project)
        summary = calc_project(project) if project.features else None
        return _project_full(project, summary)
    return _resource_dict(resource)


# ---------------------------------------------------------------------------
# POST /estimation-projects/{project_id}/resources
# ---------------------------------------------------------------------------

@router.post("/{project_id}/resources", status_code=201)
async def add_resource(
    project_id: int,
    body: ResourceCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")

    sort_order = max((r.sort_order for r in project.resources), default=0) + 1
    resource = EstimationResource(
        project_id=project_id,
        role=body.role,
        responsibility=body.responsibility,
        count=body.count,
        effort_pct=body.effort_pct,
        hourly_rate=body.hourly_rate,
        sort_order=sort_order,
        effort_hours=0.0,
        total_cost=0.0,
    )
    db.add(resource)
    await db.flush()
    await db.refresh(project)
    recalculate_project(project)
    await db.commit()
    await db.refresh(project)
    summary = calc_project(project) if project.features else None
    return _project_full(project, summary)


# ---------------------------------------------------------------------------
# DELETE /estimation-projects/{project_id}/resources/{resource_id}
# ---------------------------------------------------------------------------

@router.delete("/{project_id}/resources/{resource_id}")
async def delete_resource(
    project_id: int,
    resource_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationResource).where(
            EstimationResource.id == resource_id,
            EstimationResource.project_id == project_id,
        )
    )
    resource = result.scalar_one_or_none()
    if not resource:
        raise HTTPException(404, "Resource not found")

    await db.delete(resource)
    await db.flush()

    proj_result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = proj_result.scalar_one_or_none()
    if project:
        await db.refresh(project)
        recalculate_project(project)

    await db.commit()
    if project:
        await db.refresh(project)
        summary = calc_project(project) if project.features else None
        return _project_full(project, summary)
    return {"message": "Deleted"}


# ---------------------------------------------------------------------------
# POST /estimation-projects/{project_id}/generate  (AI endpoint)
# ---------------------------------------------------------------------------

async def _run_ai_generation(
    project_id: int,
    platform: str | None = None,
    tech_stack: dict | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    seed: int | None = None,
) -> None:
    """Background task: call Ollama and populate features."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(EstimationProject).where(EstimationProject.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                progress_push(project_id, "Project not found", "error")
                return

            if not project.document_id:
                progress_push(project_id, "No document attached to this project", "error")
                return

            # Load document
            doc_result = await db.execute(
                select(Document).where(Document.id == project.document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if not doc:
                progress_push(project_id, "Attached document not found", "error")
                return
            if doc.status != DocumentStatus.ANALYZED:
                progress_push(project_id, f"Document status is {doc.status} — must be ANALYZED", "error")
                return
            if not doc.extracted_text:
                progress_push(project_id, "Document has no extracted text", "error")
                return

            progress_push(project_id, f"Document loaded: {doc.original_filename} ({len(doc.extracted_text):,} chars)", "success")

            # Trim text — keep it short so the model responds quickly
            doc_text = doc.extracted_text[:3000]

            # Build platform + tech stack context
            platform_label = {"web": "Web Application", "mobile": "Mobile Application (iOS/Android)", "both": "Web + Mobile Application"}.get(platform or "", "Software Application")
            tech_lines = []
            if tech_stack:
                layer_labels = {
                    "frontend": "Web Frontend",
                    "mobile_framework": "Mobile Framework",
                    "backend": "Backend / API",
                    "database": "Database",
                }
                for layer, items in tech_stack.items():
                    if items:
                        label = layer_labels.get(layer, layer.replace("_", " ").title())
                        tech_lines.append(f"  - {label}: {', '.join(items)}")
            tech_context = ("\nTECH STACK:\n" + "\n".join(tech_lines)) if tech_lines else ""

            platform_instructions = ""
            if platform == "mobile":
                platform_instructions = "- Include mobile-specific features: push notifications, device permissions, offline sync, navigation, app store assets\n- Set ui_complexity to reflect mobile UI effort\n- No web-only features needed"
            elif platform == "web":
                platform_instructions = "- Include web-specific features: authentication pages, dashboards, responsive layouts, SEO, browser compatibility\n- No mobile-only features needed"
            elif platform == "both":
                platform_instructions = "- Prefix module names with 'Web - ' or 'Mobile - ' where the implementation differs\n- Include both web and mobile specific features\n- Shared backend features use no prefix"

            prompt = f"""You are a software project estimator. Read the document below and produce a detailed feature breakdown for effort estimation.

PLATFORM: {platform_label}{tech_context}

DOCUMENT:
{doc_text}

TASK: Identify 15-25 individual implementable features suited to the platform and tech stack above. For each feature output these exact fields:
- milestone: phase name (e.g. "Phase 1 - Foundation", "Phase 2 - Core Features")
- module: top-level module name (group logically, e.g. "Authentication", "Dashboard", "User Management")
- sub_module: sub-area within module (e.g. "Login", "Role Management")
- feature: specific feature or screen name
- data_model_complexity: "simple", "medium", or "complex" (null if no data model needed)
- api_complexity: "simple", "medium", or "complex" (null if no API needed)
- business_rules_complexity: "simple", "medium", or "complex" (null if no business logic)
- ui_complexity: "simple", "medium", or "complex" (null if no UI)
- fixed_hours: 0

Complexity levels:
- simple = minimal logic, 1 entity, basic CRUD
- medium = moderate logic, multiple entities, validations
- complex = complex workflows, many rules, real-time or advanced UI

Platform-specific guidance:
{platform_instructions if platform_instructions else "- Include all standard software features"}

Output format: a JSON object with key "features" containing the array.
Start your response with {{ and end with }}.
Do not include any text before or after the JSON."""

            progress_push(project_id, f"Extracted {len(doc_text):,} chars of document text", "info")
            if platform:
                progress_push(project_id, f"Platform: {platform_label}", "info")
            if tech_lines:
                progress_push(project_id, f"Stack: {' · '.join(item.strip('- ').split(': ', 1)[-1] for item in tech_lines)}", "info")
            progress_push(project_id, "Identifying modules and feature areas from document…", "working")
            progress_push(project_id, "Estimating complexity per feature (data model, API, business rules, UI)…", "working")
            progress_push(project_id, "Sending to AI model — this may take a few minutes…", "working")
            mode_desc = f"temp={temperature}" + (f" seed={seed} (deterministic)" if seed is not None else " (creative)")
            progress_push(project_id, f"AI model: {model or 'default'} · {mode_desc}", "info")
            logger.info("[EstimationProject] project_id=%s — calling ollama generate model=%s temp=%s seed=%s", project_id, model, temperature, seed)

            try:
                ai_response = await llm_client.generate(
                    prompt,
                    model=model or None,
                    temperature=temperature,
                    seed=seed,
                    max_tokens=4096,
                    timeout=900.0,
                )
            except OllamaUnavailableError as e:
                progress_push(project_id, f"AI unavailable: {e}", "error")
                return

            progress_push(project_id, f"AI responded — received {len(ai_response):,} chars, parsing…", "success")
            logger.info("[EstimationProject] project_id=%s — parsing AI response", project_id)

            data = _extract_json(ai_response)
            if not data or "features" not in data:
                progress_push(project_id, "Failed to parse AI response — invalid JSON format", "error")
                logger.error("[EstimationProject] project_id=%s — invalid AI format: %s", project_id, ai_response[:500])
                return

            raw_features: list[dict] = data["features"]
            if not isinstance(raw_features, list):
                progress_push(project_id, "AI returned malformed features array", "error")
                return

            progress_push(project_id, f"Parsed {len(raw_features)} features — calculating effort hours…", "working")

            valid_complexity = {"simple", "medium", "complex"}

            def _clean_complexity(val) -> str | None:
                if isinstance(val, str) and val.lower() in valid_complexity:
                    return val.lower()
                return None

            for idx, fdata in enumerate(raw_features):
                feat = EstimationFeature(
                    project_id=project_id,
                    sort_order=idx,
                    milestone=fdata.get("milestone") or None,
                    module=fdata.get("module") or None,
                    sub_module=fdata.get("sub_module") or None,
                    feature=str(fdata.get("feature", f"Feature {idx + 1}")),
                    data_model_complexity=_clean_complexity(fdata.get("data_model_complexity")),
                    api_complexity=_clean_complexity(fdata.get("api_complexity")),
                    business_rules_complexity=_clean_complexity(fdata.get("business_rules_complexity")),
                    ui_complexity=_clean_complexity(fdata.get("ui_complexity")),
                    fixed_hours=float(fdata.get("fixed_hours") or 0),
                )
                db.add(feat)

            await db.flush()
            await db.refresh(project)
            recalculate_project(project)
            await db.commit()

            progress_push(project_id, f"Saving {len(raw_features)} features to project…", "working")
            progress_push(
                project_id,
                f"Complete — {len(raw_features)} features · {project.grand_total_hours:.0f}h total · ₹{project.total_project_cost:,.0f}",
                "success",
            )
            logger.info(
                "[EstimationProject] project_id=%s — DONE (%d features, %.0fh, ₹%.0f)",
                project_id,
                len(raw_features),
                project.grand_total_hours,
                project.total_project_cost,
            )

        except Exception as exc:
            progress_push(project_id, f"Unexpected error: {exc}", "error")
            logger.exception("[EstimationProject] project_id=%s — unhandled exception", project_id)
            await db.rollback()


@router.post("/{project_id}/generate", status_code=202)
async def generate_features(
    project_id: int,
    background_tasks: BackgroundTasks,
    body: GenerateBody = GenerateBody(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")
    if not project.document_id:
        raise HTTPException(400, "No document attached to this project")

    # Check document exists and is analyzed
    doc_result = await db.execute(
        select(Document).where(Document.id == project.document_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Attached document not found")
    if doc.status != DocumentStatus.ANALYZED:
        raise HTTPException(400, f"Document must be ANALYZED before AI generation. Current status: {doc.status}")

    progress_clear(project_id)
    progress_init(project_id)
    progress_push(project_id, f"Starting AI feature generation for project: {project.name}", "info")

    background_tasks.add_task(
        _run_ai_generation,
        project_id,
        body.platform,
        body.tech_stack,
        body.model,
        body.temperature if body.temperature is not None else 0.7,
        body.seed,
    )
    return {"message": "AI generation started", "project_id": project_id}


# ---------------------------------------------------------------------------
# GET /estimation-projects/{project_id}/progress
# ---------------------------------------------------------------------------

@router.get("/{project_id}/progress")
async def get_generation_progress(project_id: int):
    return {"messages": progress_get(project_id)}


# ---------------------------------------------------------------------------
# POST /estimation-projects/{project_id}/chat-reestimate  (background task)
# GET  /estimation-projects/{project_id}/chat-progress
# GET  /estimation-projects/{project_id}/chat-result
# ---------------------------------------------------------------------------

# In-memory result store keyed by project_id
_chat_results: dict[int, dict] = {}


class ChatReestimateBody(BaseModel):
    message: str


async def _run_chat_reestimate(project_id: int, message: str) -> None:
    """Background task: AI advisor re-estimates project based on user instruction."""
    key = f"chat_{project_id}"
    async with AsyncSessionLocal() as db:
        try:
            progress_push(key, f"Reading project features…", "working")
            result = await db.execute(
                select(EstimationProject).where(EstimationProject.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project or not project.features:
                progress_push(key, "Project or features not found", "error")
                _chat_results[project_id] = {"error": "Project or features not found"}
                return

            feature_lines = []
            for f in project.features:
                feature_lines.append(
                    f"  id={f.id} | {f.module or 'General'} | {f.feature} | "
                    f"data_model={f.data_model_complexity or 'null'} | api={f.api_complexity or 'null'} | "
                    f"biz_rules={f.business_rules_complexity or 'null'} | ui={f.ui_complexity or 'null'} | "
                    f"fixed={f.fixed_hours}h | total={f.total_hours:.1f}h"
                )
            features_text = "\n".join(feature_lines)

            prompt = f"""You are a software project estimation AI advisor.

USER INSTRUCTION: {message}

CURRENT FEATURES:
{features_text}

CURRENT TOTALS: {project.total_dev_hours:.1f}h dev, {project.grand_total_hours:.1f}h grand total, cost approx {project.total_project_cost:,.0f}

Adjust feature complexities to satisfy the user instruction.
Rules:
- complexity values: "simple", "medium", "complex", or null (null = component not needed = 0h)
- Only return features that actually need changes
- Do not add or remove features

Return JSON object:
- "features": array of changed features, each with: id, data_model_complexity, api_complexity, business_rules_complexity, ui_complexity, fixed_hours
- "advice": 1-3 sentence plain English explanation of what was changed and why

Start with {{ and end with }}. No text before or after the JSON."""

            progress_push(key, "Sending instruction to AI model…", "working")
            logger.info("Chat re-estimate BG | project=%d | instruction=%r", project_id, message)
            resp = await llm_client.generate(prompt, max_tokens=2048, timeout=480.0)
            progress_push(key, f"AI responded ({len(resp)} chars) — parsing…", "working")

            data = _extract_json(resp)
            modified_features = data.get("features", [])
            advice = data.get("advice", "Done.")

            progress_push(key, f"Applying changes to {len(modified_features)} feature(s)…", "working")
            feat_map = {f.id: f for f in project.features}
            changed = 0
            for mf in modified_features:
                feat = feat_map.get(mf.get("id"))
                if not feat:
                    continue
                for field in ["data_model_complexity", "api_complexity", "business_rules_complexity", "ui_complexity", "fixed_hours"]:
                    if field in mf:
                        setattr(feat, field, mf[field])
                changed += 1

            recalculate_project(project)
            await db.commit()
            await db.refresh(project)

            summary = calc_project(project) if project.features else None
            project_data = _project_full(project, summary)
            _chat_results[project_id] = {
                "advice": advice,
                "changed_count": changed,
                "project": project_data,
            }
            progress_push(key, f"Complete — updated {changed} feature(s)", "success")
            logger.info("Chat re-estimate BG | project=%d | done, changed=%d", project_id, changed)

        except OllamaUnavailableError as e:
            msg = str(e)
            progress_push(key, f"Ollama unavailable: {msg}", "error")
            _chat_results[project_id] = {"error": msg}
        except Exception as e:
            logger.error("Chat re-estimate BG error: %s", e)
            progress_push(key, f"Error: {str(e)}", "error")
            _chat_results[project_id] = {"error": str(e)}


@router.post("/{project_id}/chat-reestimate", status_code=202)
async def chat_reestimate(
    project_id: int,
    body: ChatReestimateBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EstimationProject).where(EstimationProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Estimation project not found")
    if not project.features:
        raise HTTPException(400, "No features to re-estimate. Add or generate features first.")

    key = f"chat_{project_id}"
    progress_clear(key)
    progress_init(key)
    _chat_results.pop(project_id, None)
    progress_push(key, f"Starting AI advisor: {body.message[:80]}…", "info")

    background_tasks.add_task(_run_chat_reestimate, project_id, body.message)
    return {"message": "Re-estimation started", "project_id": project_id}


@router.get("/{project_id}/chat-progress")
async def get_chat_progress(project_id: int):
    return {"messages": progress_get(f"chat_{project_id}")}


@router.get("/{project_id}/chat-result")
async def get_chat_result(project_id: int):
    result = _chat_results.get(project_id)
    if result is None:
        raise HTTPException(404, "No result available yet — still processing or no run started")
    return result
