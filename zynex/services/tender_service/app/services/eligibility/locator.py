"""S5 - locate the eligibility section of a tender, deterministically (no AI).

Every tender states its bidder eligibility in one place: a section headed "Eligibility Criteria" /
"Pre-Qualification" / "Qualification Requirements", usually a table of conditions with the proof to submit.
Reading only those pages (plus a few strongly eligibility-looking extras) is what makes a run take minutes
instead of an hour on a CPU-only server, and it keeps contract boilerplate out of the checklist.

`find_core_chunks` returns the chunk ids of that section; an empty result means "no clear section found",
and the caller falls back to the vocabulary prefilter.
"""
import re
from typing import Dict, List, Set, Tuple

from app.schemas.eligibility import ChunkSchema
from app.services.eligibility.multilingual import HEADING_WORDS, count_terms, is_latin

TABLE_START, TABLE_END = "[TABLE START]", "[TABLE END]"
MAX_CONTINUATION_PAGES = 6
MAX_PROSE_PAGES = 3          # a prose eligibility section is followed for at most this many pages after its heading
MAX_CORE_PAGES = 12          # hard cap on pages read as "the eligibility section"

_HEADING = re.compile(
    r"^\W{0,4}(?:(?:section|clause|chapter|part|annexure|appendix|schedule)\s*[-–]?\s*[\dIVXLCA-Z]{1,5}\s*[:\-–.]\s*|"
    r"\d+(?:\.\d+)*[\.\)]?\s+|[IVXLC]+[\.\)]\s+|[A-Z][\.\)]\s+)?"
    r"(?:(?:technical|financial|general|commercial|minimum|basic|bidder['’]?s?|bidders['’]?|mandatory)\s*[/&,]?\s*)*"
    r"(?:pre-?\s?qualification|eligibility|qualification|qualifying|"
    r"eligible\s+(?:bidders?|tenderers?|applicants?|firms?|agenc(?:y|ies)|consultants?|contractors?))\b"
    r"(?:[^\n]{0,40}?(?:criteria|conditions?|requirements?|\(\s*[a-z]{2,4}\s*\)))?"
    r"(?:\s*(?:for|of|to)\s+(?:the\s+)?(?:bidders?|tenderers?|applicants?|bids?|participation)[^\n]{0,20})?"
    r"(?:\s*\([^)\n]{1,12}\))?\W{0,3}$", re.IGNORECASE)
_HEADING_LOOSE = re.compile(
    r"^\W{0,4}(?:\d+(?:\.\d+)*[\.\)]?\s+)?[^\n.]{0,60}\b(?:eligibility|pre-?\s?qualification|qualification\s+criteria)\b[^\n.]{0,40}$",
    re.IGNORECASE)
_SCORING_LABEL = re.compile(r"marks|score|scoring|weightage|points", re.IGNORECASE)
_OTHER_HEADING = re.compile(
    r"^\s*(?:\d{1,2}[\.\)]\s+[A-Z][A-Z0-9 ,&/\-()']{4,70}|(?:SECTION|PART|CHAPTER|ANNEXURE|APPENDIX|SCHEDULE)\b[^\n]{0,60})\s*$")
_ELIG_LABEL = re.compile(r"eligibility|pre-?qual|qualification\s*(?:criteria|requirement|condition)|^\W*criteri(?:a|on)\W*$|^\W*(?:conditions?|qualifying\s+conditions?)\W*$|^\W*(?:(?:mandatory|minimum|specific|bidder'?s?)\s+)?requirements?\W*$", re.IGNORECASE)
_STRONG_LABEL = re.compile(r"eligibility|pre-?qual|qualification\s*(?:criteria|requirement|condition)|qualifying", re.IGNORECASE)
_PROOF_LABEL = re.compile(r"proof|document|evidence|supporting|enclos|submit|certificate", re.IGNORECASE)
_DOT_LEADER = re.compile(r"\.{4,}\s*\d+\s*$|(?:\.\s){4,}", re.MULTILINE)


def is_toc(text: str) -> bool:
    return len(_DOT_LEADER.findall(text)) >= 3


def table_blocks(chunk_text: str) -> List[List[str]]:
    """Row lines of each [TABLE START]..[TABLE END] block in a chunk."""
    blocks, cur = [], None
    body = [l for l in chunk_text.split("\n") if not l.startswith("--- [PAGE")]
    first_marker = next((l.strip() for l in body if l.strip() in (TABLE_START, TABLE_END)), None)
    if first_marker == TABLE_END:          # the chunk starts in the middle of a table cut by the chunker
        cur = []
    for line in chunk_text.split("\n"):
        if line.strip() == TABLE_START:
            cur = []
        elif line.strip() == TABLE_END:
            if cur is not None:
                blocks.append(cur)
            cur = None
        elif cur is not None and line.strip() and not line.startswith("--- [PAGE"):
            cur.append(line)
    if cur:  # chunk split inside a table
        blocks.append(cur)
    return blocks


def row_cells(line: str) -> List[Tuple[str, str]]:
    """'S.No: 1 | Eligibility Conditions: text | Proof: text' -> [(label, value), ...]."""
    cells = []
    for part in re.split(r"\s\|\s", line):
        label, sep, value = part.partition(": ")
        cells.append((label.strip(), value.strip()) if sep else ("", part.strip()))
    return cells


def _table_labels(block: List[str]) -> Set[str]:
    labels: Set[str] = set()
    for line in block[:3]:
        labels.update(label for label, _ in row_cells(line) if label)
    return labels


_STRONG_NEEDS = re.compile(r"criteri|condition|requirement|eligib", re.IGNORECASE)


def _strong_header(labels: Set[str], ncols: int) -> bool:
    """A header cell naming eligibility counts only in a real multi-column checklist or when it says criteria /
    conditions / requirements. A 'Pre-Qualification | PQ' row of an abbreviations table does not."""
    return any(_STRONG_LABEL.search(l) and (ncols >= 3 or _STRONG_NEEDS.search(l)) for l in labels)


_GENERIC_LABEL = re.compile(r"^\s*(?:column\s*\d+)?\s*$", re.IGNORECASE)


def _headerless_eligibility(block: List[str]) -> bool:
    """A table with no header row ('Column 1 | Column 2 | Column 3') whose first rows carry a short cell that names
    the criteria ('Commercial Qualification Criteria') next to long requirement text. Short abbreviation tables
    ('PQC | Pre-Qualification Criteria') have no such long cell."""
    if not block or max(len(row_cells(line)) for line in block[:6]) < 3 or not all(_GENERIC_LABEL.match(l) for l in _table_labels(block) if l):
        return False
    cells = [v for line in block[:6] for _l, v in row_cells(line) if v]
    names_criteria = any(len(v.split()) <= 8 and _STRONG_LABEL.search(v) and _STRONG_NEEDS.search(v) for v in cells)
    return names_criteria and any(len(v) >= 80 for v in cells)


def has_eligibility_table(chunk_text: str) -> bool:
    for block in table_blocks(chunk_text):
        labels = _table_labels(block)
        if any(_SCORING_LABEL.search(l) for l in labels):
            continue                       # evaluation-scoring tables (Criteria | Max Marks) are not bidder eligibility
        if _strong_header(labels, len(row_cells(block[0])) if block else 0) or _headerless_eligibility(block):
            return True
        if any(_ELIG_LABEL.search(l) for l in labels) and any(_PROOF_LABEL.search(l) for l in labels):
            return True
    return False


def _multilingual_heading(line: str) -> bool:
    """A short heading line naming eligibility in Hindi, Tamil, Telugu... (no full stop)."""
    return (len(line.split()) <= 9 and not line.endswith((".", ",", ";", "\u0964"))
            and count_terms(line, HEADING_WORDS) >= 1)


def _find_heading(chunk_text: str):
    """(heading line, only a footer / page number follows it) for the first eligibility heading, else None."""
    lines = [l.strip() for l in chunk_text.split("\n") if l.strip() and not l.startswith("--- [PAGE")]
    in_table, table_line = False, set()                 # a row of a table is data, never a section heading
    for i, line in enumerate(lines):
        if line == TABLE_START:
            in_table = True
        elif line == TABLE_END:
            in_table = False
        elif in_table or " | " in line:
            table_line.add(i)
    for i, line in enumerate(lines):
        if i in table_line:
            continue
        words = line.split()
        loose = (_HEADING_LOOSE.match(line) and len(words) <= 10 and not line.endswith((".", ","))
                 and (line.isupper() or sum(w[:1].isupper() for w in words) >= 0.7 * len(words)))
        if len(line) <= 90 and not _DOT_LEADER.search(line) and (_HEADING.match(line) or loose or _multilingual_heading(line)):
            substantive = any(len(l.split()) >= 6 or re.match(r"^(?:\d+(?:\.\d+)*[\.\)]?|\(?[a-z]\)|[ivx]+\.)\s", l, re.I)
                              or l.startswith("[TABLE") for l in lines[i + 1:])
            return line, not substantive
    return None


def heading_position(chunk_text: str) -> Tuple[bool, bool]:
    """(has an eligibility heading, heading sits at the very end of the page)."""
    found = _find_heading(chunk_text)
    return (True, found[1]) if found else (False, False)


_NUMBER = re.compile(r"^\W{0,4}(\d+(?:\.\d+)*)[\.\)]?\s+")


def _clause_number(line: str):
    m = _NUMBER.match(line)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _trim(chunk: ChunkSchema, start_line: str = "", end_number=None) -> ChunkSchema:
    """The chunk without the text before the eligibility heading and/or from the next clause heading on.
    Keeps the AI on the section itself instead of the neighbouring clauses (less to read, fewer stray criteria)."""
    text = chunk.chunk_text
    head = text.split("\n", 1)[0] + "\n" if text.startswith("--- [PAGE") else ""
    body = text[len(head):]
    if start_line:
        idx = body.find(start_line)
        body = body[idx:] if idx >= 0 else body
    if end_number:
        nxt = ".".join(map(str, end_number))
        m = re.search(rf"^[ \t]*{re.escape(nxt)}[\.\)]?[ \t]+[A-Z][^\n]{{2,80}}$", body, re.MULTILINE)
        if m and m.start() > 0:
            body = body[:m.start()]
    if not body.strip() or body == text[len(head):]:
        return chunk                       # nothing was cut (or nothing would be left)
    new = head + body
    return chunk.model_copy(update={"chunk_text": new, "char_count": len(new)})


def _next_clause_in(chunk_text: str, number) -> bool:
    nxt = ".".join(map(str, number))
    return bool(re.search(rf"^[ \t]*{re.escape(nxt)}[\.\)]?[ \t]+[A-Z][^\n]{{2,80}}$", chunk_text, re.MULTILINE))


def block_is_eligibility(block: List[str]) -> bool:
    labels = _table_labels(block)
    if any(_SCORING_LABEL.search(l) for l in labels):
        return False
    return (_strong_header(labels, len(row_cells(block[0])) if block else 0) or _headerless_eligibility(block)
            or (any(_ELIG_LABEL.search(l) for l in labels) and any(_PROOF_LABEL.search(l) for l in labels)))


def _row_like(line: str) -> bool:
    return bool(re.match(r"^[^|:]{1,60}: .*", line.strip()))


_OTHER_HEADING_LOCAL = re.compile(r"^\s*\d{1,2}[\.\)]\s+\S[^\n]{2,60}$")


def _local_heading(line: str) -> bool:
    """A short numbered heading in another script ('6. भुगतान की शर्तें'): no full stop, a few words."""
    return bool(_OTHER_HEADING_LOCAL.match(line)) and not is_latin(line) and len(line.split()) <= 8 \
        and not line.rstrip().endswith((".", ",", ";", "\u0964"))


def has_other_heading(chunk_text: str) -> bool:
    """A numbered ALL-CAPS heading / SECTION / ANNEXURE line that is not an eligibility heading."""
    for line in chunk_text.split("\n"):
        line = line.strip()
        if line and len(line) <= 90 and not _DOT_LEADER.search(line) and not _HEADING.match(line) \
                and (_OTHER_HEADING.match(line) or _local_heading(line)):
            return True
    return False


def find_core_chunks(chunks: List[ChunkSchema]) -> List[ChunkSchema]:
    """Chunks that make up the tender's eligibility section, in document order."""
    chunks = sorted(chunks, key=lambda c: (c.physical_page, c.chunk_id))
    core: Dict[str, ChunkSchema] = {}
    runs: Dict[int, str] = {}               # chunk index -> "table" | "prose": how to follow it onto later pages
    heads: Dict[int, Tuple[str, object]] = {}   # prose chunk index -> (heading line, the next clause number to stop at)
    for i, c in enumerate(chunks):
        if is_toc(c.chunk_text):
            continue
        found = _find_heading(c.chunk_text)
        has_heading, at_end = (True, found[1]) if found else (False, False)
        table = has_eligibility_table(c.chunk_text)
        if table or (has_heading and not at_end):
            core[c.chunk_id] = c
            runs[i] = "table" if table else "prose"
            if not table and found:
                num = _clause_number(found[0])
                heads[i] = (found[0], (num[:-1] + (num[-1] + 1,)) if num else None)
        if at_end and i + 1 < len(chunks) and not is_toc(chunks[i + 1].chunk_text):
            core[chunks[i + 1].chunk_id] = chunks[i + 1]    # heading printed last on a page: content follows
            runs[i + 1] = "table" if has_eligibility_table(chunks[i + 1].chunk_text) else "prose"

    for start, kind in sorted(runs.items()):
        labels = set()
        for block in table_blocks(chunks[start].chunk_text):
            labels |= _table_labels(block)
        budget, j = (MAX_CONTINUATION_PAGES if kind == "table" else MAX_PROSE_PAGES), start + 1
        while budget > 0 and j < len(chunks):
            nxt = chunks[j]
            if is_toc(nxt.chunk_text):
                break
            same_page = nxt.physical_page == chunks[j - 1].physical_page      # the chunker cut a long page in two
            body = [l for l in nxt.chunk_text.split("\n")[1:] if l.strip()]
            if kind == "table":
                blocks = table_blocks(nxt.chunk_text)
                first_is_table = bool(body) and (body[0].strip() == TABLE_START or _row_like(body[0]))
                same_labels = bool(blocks) and any(_table_labels(b) <= labels or block_is_eligibility(b) for b in blocks)
                if not (same_page and (first_is_table or same_labels)) and not (first_is_table and same_labels):
                    break
            else:                                  # prose section: runs until the next top-level heading
                stop = heads.get(start, ("", None))[1]
                if stop and _next_clause_in(nxt.chunk_text, stop):
                    tail = _trim(nxt, end_number=stop)                 # the section's tail, before the next clause
                    if tail is not nxt:                                # nothing precedes the heading: no tail at all
                        core[nxt.chunk_id] = tail
                    break
                if has_other_heading(nxt.chunk_text):
                    break
            core[nxt.chunk_id] = nxt
            budget -= 1
            j += 1
    for i, (line, _stop) in heads.items():           # start a prose section at its heading, not at the top of the page
        cid = chunks[i].chunk_id
        if cid in core and core[cid] is chunks[i]:
            core[cid] = _trim(chunks[i], start_line=line, end_number=_stop)
    ordered = sorted(core.values(), key=lambda c: (c.physical_page, c.chunk_id))
    if len(ordered) > MAX_CORE_PAGES:                  # keep the pages that carry eligibility tables / headings first
        strong = [c for c in ordered if has_eligibility_table(c.chunk_text) or heading_position(c.chunk_text)[0]]
        rest = [c for c in ordered if c not in strong]
        ordered = sorted((strong + rest)[:MAX_CORE_PAGES], key=lambda c: (c.physical_page, c.chunk_id))
    return ordered
