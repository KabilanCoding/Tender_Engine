from app.parsers.base_parser import BaseParser
from app.parsers.document_parser import DocumentParser


def get_parser(filename: str) -> BaseParser:
    """Return the parser for a file (PDF, DOCX and TXT are handled in pure Python)."""
    return DocumentParser()
