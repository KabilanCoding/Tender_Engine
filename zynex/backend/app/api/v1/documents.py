import os
import re
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.dependencies import get_db
from app.core.security import decode_token, oauth2_scheme
from app.core import file_store
from app.core.config import settings
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.project_documents import TenderChunk
from app.parsers.parser_factory import get_parser
from app.ai.llm_client import llm_client, OllamaUnavailableError
from app.ai.prompt_templates import document_classification_prompt
from app.ai.text_chunker import chunk_text
from app.api.v1.progress_store import init as prog_init, push as prog_push, get as prog_get
from datetime import datetime, timezone
import json


def _extract_json(text: str) -> dict:
    """Robustly extract JSON from LLM response that may have markdown/extra text."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: int
    original_filename: str
    doc_type: str
    status: str
    page_count: Optional[int]

    class Config:
        from_attributes = True


def _doc_key(doc_id: int) -> str:
    return f"doc_{doc_id}"


async def process_document(doc_id: int, file_bytes: bytes, filename: str):
    from app.core.database import AsyncSessionLocal
    key = _doc_key(doc_id)
    prog_init(key)
    prog_push(key, f"Received '{filename}' — starting processing…", "info")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return

        try:
            doc.status = DocumentStatus.PROCESSING
            await db.commit()

            # 1. Parse
            prog_push(key, "Extracting text from the document…", "working")
            parser = get_parser(filename)
            parsed = await parser.parse(file_bytes, filename)
            doc.extracted_text = parsed.text
            doc.page_count = parsed.page_count
            doc.mime_type = parsed.mime_type
            char_count = len(parsed.text or "")
            prog_push(key, f"Extracted {char_count:,} characters — {parsed.page_count or '?'} pages", "success")

            # 2. Classify with AI
            prog_push(key, "Classifying document type with AI…", "working")
            prompt = document_classification_prompt(parsed.text)
            ai_response = await llm_client.generate(prompt)
            classification = _extract_json(ai_response)
            raw_type = classification.get("doc_type", "UNKNOWN")
            try:
                doc.doc_type = DocumentType(raw_type)
            except ValueError:
                doc.doc_type = DocumentType.UNKNOWN
            prog_push(key, f"Document classified as: {doc.doc_type.value}", "success")
            doc.status = DocumentStatus.ANALYZED
            await db.commit()

            # 3. Chunk + embed for RAG
            chunks = chunk_text(parsed.text or "")
            prog_push(key, f"Splitting into {len(chunks)} text chunks for indexing…", "info")
            now = datetime.now(timezone.utc)
            embedded = 0
            for ch in chunks:
                try:
                    embedding_vec = await llm_client.embed(ch.chunk_text)
                    stored_vector = embedding_vec
                    embedded += 1
                except OllamaUnavailableError:
                    stored_vector = None

                db.add(TenderChunk(
                    document_id=doc.id,
                    chunk_index=ch.chunk_index,
                    chunk_text=ch.chunk_text,
                    section_heading=ch.section_heading,
                    chunk_metadata={"source": doc.original_filename},
                    embedding=stored_vector,
                    created_at=now,
                ))

            prog_push(key, f"Indexed {embedded}/{len(chunks)} chunks with embeddings", "success")
            prog_push(key, "Document ready — you can now run eligibility analysis", "success")

        except Exception as e:
            doc.status = DocumentStatus.FAILED
            prog_push(key, f"Processing failed: {e}", "error")
        finally:
            await db.commit()


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    allowed = {".pdf", ".docx", ".txt"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, "File too large")

    file_path = await file_store.save(["tenders"], file.filename, file_bytes)

    doc = Document(
        filename=os.path.basename(file_path),
        original_filename=file.filename,
        file_path=file_path,
        uploaded_by=int(decode_token(token).get("sub")),
    )
    db.add(doc)
    await db.flush()
    doc_id = doc.id
    await db.commit()

    background_tasks.add_task(process_document, doc_id, file_bytes, file.filename)
    return doc


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return result.scalars().all()


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{doc_id}/progress")
async def get_document_progress(doc_id: int):
    """Poll progress messages for document parsing."""
    return {"messages": prog_get(_doc_key(doc_id))}


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    await file_store.delete(doc.file_path)
    # Remove associated tender chunks
    await db.execute(sa_delete(TenderChunk).where(TenderChunk.document_id == doc_id))
    await db.delete(doc)
    await db.commit()
