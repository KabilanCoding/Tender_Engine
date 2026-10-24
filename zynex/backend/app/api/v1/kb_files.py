"""Documents kept for knowledge-base facts: upload, list, download, delete.

Files are kept in the document storage (app.core.file_store: this machine or the file server) under
kb/<owner_type>/<owner_key>/<id>_<name>; the kb_files table keeps the full path.
Same access rule as the rest of the knowledge base (everyone reads, admins write).
"""
import mimetypes
import os
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import file_store
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import decode_token, oauth2_scheme
from app.models.knowledge_base import Certification, KbFile

router = APIRouter(prefix="/kb/files", tags=["knowledge-base"])

OWNER_TYPES = {"profile", "certification", "financial", "office", "oem", "client", "employee", "technology"}
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".doc", ".xlsx", ".xls", ".txt"}


class KbFileOut(BaseModel):
    id: int
    owner_type: str
    owner_key: str
    original_filename: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _check_owner(owner_type: str, owner_key: str) -> None:
    if owner_type not in OWNER_TYPES:
        raise HTTPException(400, f"Unknown owner type '{owner_type}'.")
    if not owner_key or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", owner_key):
        raise HTTPException(400, "Invalid owner key.")


@router.get("", response_model=List[KbFileOut])
async def list_files(owner_type: Optional[str] = None, owner_key: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """All files, or those of one owner type / one owner (e.g. owner_type=profile&owner_key=pan)."""
    q = select(KbFile).order_by(KbFile.created_at.desc(), KbFile.id.desc())
    if owner_type:
        q = q.where(KbFile.owner_type == owner_type)
    if owner_key:
        q = q.where(KbFile.owner_key == owner_key)
    return (await db.execute(q)).scalars().all()


@router.post("", response_model=KbFileOut, status_code=201)
async def upload_file(owner_type: str = Form(...), owner_key: str = Form(...), note: Optional[str] = Form(None),
                      file: UploadFile = File(...), db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)):
    _check_owner(owner_type, owner_key)
    name = os.path.basename(file.filename or "file")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"File type {ext or '(none)'} is not allowed. Use PDF, an image, Word, Excel or text.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.")
    path = await file_store.save(["kb", owner_type, owner_key], name, data)
    try:
        user = int(decode_token(token).get("sub") or 0) or None
    except Exception:
        user = None
    row = KbFile(owner_type=owner_type, owner_key=owner_key, original_filename=name, file_path=path,
                 mime_type=file.content_type or mimetypes.guess_type(name)[0], size_bytes=len(data), note=note, uploaded_by=user)
    db.add(row)
    if owner_type == "certification" and owner_key.isdigit():      # keep the certificate's own document_path pointing at the latest file
        cert = await db.get(Certification, int(owner_key))
        if cert:
            cert.document_path = path
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{file_id}/download")
async def download_file(file_id: int, inline: bool = False, db: AsyncSession = Depends(get_db)):
    row = await db.get(KbFile, file_id)
    if not row:
        raise HTTPException(404, "File not found")
    return file_store.response(await file_store.read(row.file_path), row.original_filename, row.mime_type, inline)


@router.delete("/{file_id}", status_code=204)
async def delete_file(file_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(KbFile, file_id)
    if not row:
        raise HTTPException(404, "File not found")
    path = row.file_path
    if row.owner_type == "certification" and row.owner_key.isdigit():
        cert = await db.get(Certification, int(row.owner_key))
        if cert and cert.document_path == path:
            cert.document_path = None
    await db.delete(row)
    await db.commit()
    await file_store.delete(path)
