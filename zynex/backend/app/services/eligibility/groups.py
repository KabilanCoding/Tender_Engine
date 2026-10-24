"""Bidder categories (lots / packages / classes): which requirements apply to which kind of bidder.

Many tenders offer several bidder categories ("Category 1: start-ups", "Category 2: local firms", "Category 3: national firms") with a
separate eligibility table for each, and a bidder applies under ONE of them. Judging the three tables together makes every company look
ineligible for something. This module finds the category heading above each table or clause (carrying it onto the next pages, where a table
continues without repeating its heading) so each requirement can be labelled with the category it belongs to.
"""
import re
from typing import Dict, List, Optional, Tuple

from app.schemas.eligibility import ChunkSchema

_KIND = r"(?:category|cat\.?|lot|package|class)"
_ID = r"(\d{1,2}|[ivx]{1,4}|[a-d])"
_GROUP = re.compile(rf"\b{_KIND}\s*[-–:.]?\s*{_ID}\b(?![\w/])", re.IGNORECASE)
_HEADLIKE = re.compile(r"criteria|eligibility|qualification|requirement|\bpq\b|\btq\b|marking|evaluation|firms?|start-?ups?|bidders?|companies|"
                       r"empanel|scope|applicable|who can", re.IGNORECASE)
_NUMBERED = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?=\S)")
_MAX_HEADING_WORDS = 22


def _key(kind: str, ident: str) -> str:
    kind = {"cat": "Category", "cat.": "Category"}.get(kind.lower(), kind.capitalize())
    return f"{kind} {ident.upper()}"


def _heading(line: str) -> Optional[Tuple[str, str]]:
    """(key, label) when this line is a heading that names a bidder category, else None."""
    s = line.strip()
    if not s or len(s.split()) > _MAX_HEADING_WORDS or len(s) > 170:
        return None
    m = _GROUP.search(s)
    if not m:
        return None
    if not (_NUMBERED.match(s) or _HEADLIKE.search(s) or re.match(rf"^\W*{_KIND}\b", s, re.IGNORECASE)):
        return None
    kind = re.match(r"[A-Za-z.]+", m.group(0)).group(0).rstrip(".")
    key = _key(kind, m.group(1))
    tail = s[m.end():].strip(" -–—:.,;)")
    label = f"{key} — {tail[:70]}" if tail and len(tail) > 2 else key
    return key, label


def _is_other_heading(line: str) -> bool:
    """A numbered heading that is not about a category ('2.5 Technical Evaluation'): the category carried so far ends here."""
    s = line.strip()
    return bool(_NUMBERED.match(s)) and len(s.split()) <= 12 and not _GROUP.search(s) and not s.rstrip().endswith((".", ";", ","))


def scan(text: str) -> List[Tuple[int, Optional[str], Optional[str]]]:
    """[(position, key, label)] for every category heading in the text; (position, None, None) where a different numbered section starts."""
    out, pos = [], 0
    for line in text.split("\n"):
        h = _heading(line)
        if h:
            out.append((pos, h[0], h[1]))
        elif _is_other_heading(line):
            out.append((pos, None, None))
        pos += len(line) + 1
    return out


class GroupIndex:
    """The category in force at the start of each chunk, and the headings inside it."""

    def __init__(self, chunks: List[ChunkSchema]):
        self.start: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        self.inside: Dict[str, List[Tuple[int, Optional[str], Optional[str]]]] = {}
        cur: Tuple[Optional[str], Optional[str]] = (None, None)
        self.labels: Dict[str, str] = {}
        for c in sorted(chunks, key=lambda c: (c.physical_page, c.chunk_id)):
            self.start[c.chunk_id] = cur
            heads = scan(c.chunk_text or "")
            self.inside[c.chunk_id] = heads
            for _p, key, label in heads:
                cur = (key, label)
                if key and label and (key not in self.labels or len(label) > len(self.labels[key])):
                    self.labels[key] = label

    def group_for(self, chunk: ChunkSchema, quote: str = "") -> Optional[str]:
        """Label of the category a requirement quoted from this chunk belongs to (None = applies to every bidder)."""
        text = chunk.chunk_text or ""
        at = text.find(quote[:60]) if quote else -1
        key, label = self.start.get(chunk.chunk_id, (None, None))
        for p, k, lab in self.inside.get(chunk.chunk_id, []):
            if at < 0 or p <= at:
                key, label = k, lab
        return self.labels.get(key, label) if key else None
