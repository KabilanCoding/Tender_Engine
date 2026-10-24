"""
Project Document API — upload, list, delete documents attached to KB projects.
Ingestion pipeline runs as a background task:
  parse → TextChunker → bge-m3 → store ProjectDocumentChunk rows
"""
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core import file_store
from app.core.dependencies import get_db
from app.core.config import settings
from app.models.project_documents import ProjectDocument, ProjectDocumentChunk
from app.parsers.parser_factory import get_parser
from app.ai.text_chunker import chunk_text
from app.ai.llm_client import llm_client, OllamaUnavailableError

router = APIRouter(prefix="/kb/projects", tags=["project-documents"])

ALLOWED_CATEGORIES = {
    "SRS", "TECHNICAL_PROPOSAL", "COMMERCIAL_PROPOSAL", "SOW",
    "ARCHITECTURE_DOC", "FLOW_DIAGRAMS", "TEST_CASES", "UAT_REPORT",
    "COMPLETION_CERT", "LESSONS_LEARNED", "CONTRACT", "OTHER",
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProjectDocumentOut(BaseModel):
    id: int
    project_id: int
    doc_category: str
    original_filename: str
    file_size_bytes: Optional[int]
    page_count: Optional[int]
    is_processed: bool
    processing_error: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ChunkOut(BaseModel):
    id: int
    chunk_index: int
    section_heading: Optional[str]
    chunk_text: str

    class Config:
        from_attributes = True


# ── Ingestion pipeline (background task) ─────────────────────────────────────

async def _ingest_document(doc_id: int, file_bytes: bytes, filename: str):
    """Parse → chunk → embed → store.  Updates ProjectDocument.is_processed when done."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return

        try:
            # 1. Parse (from the uploaded bytes: the stored copy may be on the file server)
            parser = get_parser(filename)
            parse_result = await parser.parse(file_bytes, filename)
            raw_text = parse_result.text or ""

            # 2. Chunk
            chunks = chunk_text(raw_text)

            # 3. Embed + store each chunk
            now = datetime.now(timezone.utc)
            for ch in chunks:
                try:
                    embedding_vec = await llm_client.embed(ch.chunk_text)
                    stored_vector = embedding_vec
                except OllamaUnavailableError:
                    stored_vector = None

                db_chunk = ProjectDocumentChunk(
                    project_document_id=doc.id,
                    project_id=doc.project_id,
                    chunk_index=ch.chunk_index,
                    chunk_text=ch.chunk_text,
                    section_heading=ch.section_heading,
                    doc_category=doc.doc_category,
                    chunk_metadata={"source": doc.original_filename},
                    embedding=stored_vector,
                    created_at=now,
                )
                db.add(db_chunk)

            doc.is_processed = True
            doc.processing_error = None
            doc.page_count = parse_result.page_count

        except Exception as exc:
            doc.is_processed = False
            doc.processing_error = str(exc)

        await db.commit()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{project_id}/documents", response_model=ProjectDocumentOut, status_code=201)
async def upload_project_document(
    project_id: int,
    background_tasks: BackgroundTasks,
    doc_category: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if doc_category not in ALLOWED_CATEGORIES:
        raise HTTPException(400, f"Invalid doc_category. Allowed: {sorted(ALLOWED_CATEGORIES)}")

    # filed by project and category, like the other knowledge-base documents: kb/project/<project id>/<CATEGORY>/<id>_<name>,
    # in the document storage (this machine or the file server)
    safe_name = Path(file.filename or "file").name  # strip path traversal
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.")
    dest_path = await file_store.save(["kb", "project", str(project_id), doc_category], safe_name, data)
    now = datetime.now(timezone.utc)

    doc = ProjectDocument(
        project_id=project_id,
        doc_category=doc_category,
        original_filename=safe_name,
        file_path=dest_path,
        mime_type=file.content_type,
        file_size_bytes=len(data),
        is_processed=False,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Kick off ingestion in the background
    background_tasks.add_task(_ingest_document, doc.id, data, safe_name)

    return doc


@router.get("/{project_id}/documents", response_model=list[ProjectDocumentOut])
async def list_project_documents(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectDocument)
        .where(ProjectDocument.project_id == project_id)
        .order_by(ProjectDocument.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{project_id}/documents/{doc_id}/download")
async def download_project_document(project_id: int, doc_id: int, inline: bool = True, db: AsyncSession = Depends(get_db)):
    """The uploaded file itself (to view in the browser or save), not its extracted text."""
    doc = (await db.execute(select(ProjectDocument).where(ProjectDocument.id == doc_id, ProjectDocument.project_id == project_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return file_store.response(await file_store.read(doc.file_path), doc.original_filename, doc.mime_type, inline)


@router.delete("/{project_id}/documents/{doc_id}", status_code=204)
async def delete_project_document(
    project_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.id == doc_id,
            ProjectDocument.project_id == project_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    await file_store.delete(doc.file_path)

    await db.execute(
        delete(ProjectDocumentChunk).where(ProjectDocumentChunk.project_document_id == doc_id)
    )
    await db.delete(doc)
    await db.commit()


@router.get("/{project_id}/documents/{doc_id}/chunks", response_model=list[ChunkOut])
async def list_document_chunks(
    project_id: int,
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectDocumentChunk)
        .where(
            ProjectDocumentChunk.project_document_id == doc_id,
            ProjectDocumentChunk.project_id == project_id,
        )
        .order_by(ProjectDocumentChunk.chunk_index)
    )
    return result.scalars().all()
