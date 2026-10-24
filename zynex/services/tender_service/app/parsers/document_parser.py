"""Pure-Python document text extraction (PDF, DOCX, TXT): no external parser service needed."""
import asyncio
import io
import math

from app.parsers.base_parser import BaseParser, ParseResult

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # pragma: no cover
    import fitz

_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}
_CHARS_PER_PAGE = 3000  # DOCX has no fixed pages; estimate so page counts stay meaningful

SUPPORTED_EXTENSIONS = tuple(f".{e}" for e in _MIME)


class UnsupportedDocumentError(ValueError):
    pass


def _extension(filename: str) -> str:
    return filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


def _parse_pdf(data: bytes) -> ParseResult:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.is_encrypted:
            raise UnsupportedDocumentError("The PDF is password protected.")
        pages = [page.get_text() for page in doc]
        return ParseResult(text="\f".join(pages), page_count=max(1, len(pages)), mime_type=_MIME["pdf"], metadata={})
    finally:
        doc.close()


def _parse_docx(data: bytes) -> ParseResult:
    from docx import Document  # python-docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(io.BytesIO(data))
    lines = []
    # walk the body in document order so tables stay between the paragraphs they belong to
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            text = Paragraph(child, document).text.strip()
            if text:
                lines.append(text)
        elif child.tag == qn("w:tbl"):
            for row in Table(child, document).rows:
                cells = []
                for cell in row.cells:
                    value = " ".join(cell.text.split())
                    if not cells or value != cells[-1]:   # merged cells repeat their text
                        cells.append(value)
                if any(cells):
                    lines.append("| " + " | ".join(cells) + " |")
    text = "\n".join(lines)
    return ParseResult(text=text, page_count=max(1, math.ceil(len(text) / _CHARS_PER_PAGE)),
                       mime_type=_MIME["docx"], metadata={})


def _parse_txt(data: bytes) -> ParseResult:
    text = data.decode("utf-8", errors="replace")
    return ParseResult(text=text, page_count=max(1, math.ceil(len(text) / _CHARS_PER_PAGE)),
                       mime_type=_MIME["txt"], metadata={})


class DocumentParser(BaseParser):
    async def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        ext = _extension(filename)
        if ext == "pdf":
            return await asyncio.to_thread(_parse_pdf, file_bytes)
        if ext == "docx":
            return await asyncio.to_thread(_parse_docx, file_bytes)
        if ext == "txt":
            return await asyncio.to_thread(_parse_txt, file_bytes)
        if ext == "doc":
            raise UnsupportedDocumentError("Legacy .doc files are not supported; save the file as .docx or PDF.")
        raise UnsupportedDocumentError(f"Unsupported file type '.{ext}'. Supported: PDF, DOCX, TXT.")
