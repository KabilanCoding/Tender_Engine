"""
Semantic text chunker for RAG ingestion pipeline.

Strategy:
  - Split at markdown/document headings first (preserves context boundaries)
  - Then split long segments by sentence to hit the target token range
  - Slide a 50-token overlap window between consecutive chunks

Target: 400-600 tokens per chunk (1 token ≈ 4 chars as heuristic).
"""
import re
from dataclasses import dataclass

# Heuristic: average English token is ~4 chars
CHARS_PER_TOKEN = 4
TARGET_MIN = 400 * CHARS_PER_TOKEN   # 1600 chars
TARGET_MAX = 600 * CHARS_PER_TOKEN   # 2400 chars
OVERLAP_TOKENS = 50
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN  # 200 chars

# Matches Markdown headings (# / ## / ###) or ALL-CAPS lines (common in PDFs)
_HEADING_RE = re.compile(
    r"^(#{1,6}\s+.+|[A-Z][A-Z0-9 \-:]{4,})\s*$",
    re.MULTILINE,
)

# Sentence boundary: period / exclamation / question followed by space or newline
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class TextChunk:
    chunk_index: int
    chunk_text: str
    section_heading: str | None
    page_number: int | None  # populated externally if page markers exist


def _split_by_heading(text: str) -> list[tuple[str | None, str]]:
    """Split text into (heading, body) sections."""
    sections: list[tuple[str | None, str]] = []
    last_heading: str | None = None
    last_end = 0

    for m in _HEADING_RE.finditer(text):
        body = text[last_end: m.start()].strip()
        if body:
            sections.append((last_heading, body))
        last_heading = m.group(0).strip()
        last_end = m.end()

    # Remaining body after last heading
    tail = text[last_end:].strip()
    if tail:
        sections.append((last_heading, tail))

    return sections


def _split_long_segment(text: str, heading: str | None) -> list[tuple[str | None, str]]:
    """Break a body that exceeds TARGET_MAX into sentence-boundary chunks."""
    if len(text) <= TARGET_MAX:
        return [(heading, text)]

    sentences = _SENTENCE_END_RE.split(text)
    result: list[tuple[str | None, str]] = []
    buf = ""

    for sent in sentences:
        if len(buf) + len(sent) + 1 > TARGET_MAX and len(buf) >= TARGET_MIN:
            result.append((heading, buf.strip()))
            # Overlap: keep last OVERLAP_CHARS of previous buffer
            buf = buf[-OVERLAP_CHARS:] + " " + sent
        else:
            buf = (buf + " " + sent).strip() if buf else sent

    if buf.strip():
        result.append((heading, buf.strip()))

    return result


def chunk_text(text: str) -> list[TextChunk]:
    """
    Main entry point.  Returns a list of TextChunk objects ready for embedding.
    """
    if not text or not text.strip():
        return []

    raw_sections = _split_by_heading(text)

    # Further split sections that are too long
    fine: list[tuple[str | None, str]] = []
    for heading, body in raw_sections:
        fine.extend(_split_long_segment(body, heading))

    # Merge very short consecutive segments from the same heading
    merged: list[tuple[str | None, str]] = []
    for heading, body in fine:
        if (
            merged
            and merged[-1][0] == heading
            and len(merged[-1][1]) + len(body) <= TARGET_MAX
        ):
            merged[-1] = (heading, merged[-1][1] + " " + body)
        else:
            merged.append((heading, body))

    chunks = [
        TextChunk(
            chunk_index=idx,
            chunk_text=body.strip(),
            section_heading=heading,
            page_number=None,
        )
        for idx, (heading, body) in enumerate(merged)
        if body.strip()
    ]

    return chunks
