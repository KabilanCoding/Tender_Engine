import re
from typing import List, Dict, Any, Optional
from app.services.eligibility.pipeline_log import log_pipeline_step

class StructureAnalyzer:
    """
    S3 Structure Analyzer: Detects document hierarchy (chapter, section, clause, table)
    and reconstructs multi-row and cross-page tables.
    Enforces strict structural separation between chapter, section, and sub-clause identifiers.
    """

    # Regex for numbered sections like "1. INTRODUCTION", "2. QUALIFICATION REQUIREMENTS"
    RE_SECTION_NUM = re.compile(r"^(?:[1-9]\d*)\.\s+[A-Z][A-Z\s]{2,}")
    # Title-case numbered heading ("2. Eligibility Criteria"): only trusted when the PDF font marks it as a heading
    RE_SECTION_TITLE = re.compile(r"^[1-9]\d*\.\s+[A-Z][A-Za-z &/,\-()]{2,70}$")
    # Explicit chapter labels, upper-case or Title-case only (so "part of the work..." and "section shall be" are text)
    RE_CHAPTER_TITLE = re.compile(
        r"^(?:SECTION|PART|CHAPTER|ANNEXURE|APPENDIX|SCHEDULE|Section|Part|Chapter|Annexure|Appendix|Schedule)"
        r"[\s\-–:]*(?:[0-9]+|[IVXLC]+\b|[A-Z]\b)(?![a-z])(?:\s*[-–:.]\s*\S.*)?$")
    # Clause numbers: "3.1.2", "3.1 The bidder...", "3.1. The bidder", "Clause 12", "1(a)", "(a)", "a)", "(i)", "iv.", "a. Text"
    RE_CLAUSE_NUM = re.compile(
        r"^(?:"
        r"(?:Clause\s+|Sub-clause\s+|Para\s+|Section\s+)?[1-9]\d*\.[0-9]+(?:\.[0-9]+)+\.?"
        r"|(?:Clause\s+|Sub-clause\s+|Para\s+)[1-9]\d*(?:\.[0-9]+)?"
        r"|[1-9]\d*\.[0-9]+\.?(?=\s+(?-i:[A-Z]))"
        r"|[1-9]\d*\([a-z0-9]+\)"
        r"|\([a-z]{1,2}\)(?=\s)|\((?:[ivx]{1,5})\)(?=\s)|[a-z]\)(?=\s)|(?:i{1,3}|iv|vi{0,3}|ix|x)\.(?=\s+(?-i:[A-Z]))"
        r"|[a-f]\.\s+(?-i:[A-Z])"
        r")",
        re.IGNORECASE
    )
    RE_UNIT_AFTER = re.compile(
        r"\s*(?:%|percent\b|rs\b|inr\b|hrs?\b|hours?\b|crores?\b|lakhs?\b|lacs?\b|million\b|"
        r"years?\b|months?\b|days?\b|times\b|x\b)", re.IGNORECASE)

    _TOC_LINE = re.compile(r"\.{4,}\s*\d*\s*$|(?:\.\s){4,}\d*\s*$")

    @staticmethod
    def _is_numbered_heading(first_line: str, block_text: str) -> bool:
        """'2.11 Eligible Bidders' / '2.11.1 Technical Strength': a short Title-Case line on its own, no full stop."""
        if "\n" in block_text.strip() or len(first_line) > 72 or first_line.endswith((".", ",", ";")):
            return False
        title = re.sub(r"^\W*(?:Clause\s+|Section\s+)?\d+(?:\.\d+)*\.?\s+", "", first_line)
        words = title.split()
        if not 1 <= len(words) <= 8 or not title[:1].isupper():
            return False
        return sum(w[:1].isupper() or not w[:1].isalpha() for w in words) >= 0.7 * len(words)

    ADDRESS_KEYWORDS = ["road", "street", "building", "fax", "tel:", "email:", "pin -", "po:"]
    _ADDRESS_RE = re.compile(r"(?<![a-z])(?:road|street|building|fax|tel:|email:|pin\s*-|po:)(?![a-z])", re.IGNORECASE)
    CHAPTER_WORDS = ("TENDER", "ELIGIBILITY", "REQUIREMENT", "SPECIFICATION", "CONDITIONS")

    @classmethod
    def _clause_prefix(cls, line: str) -> Optional[str]:
        """The clause number at the start of `line`, or None (amounts such as '5.5 Crore' are not clauses)."""
        m = cls.RE_CLAUSE_NUM.match(line)
        if not m or cls.RE_UNIT_AFTER.match(line[m.end():]):
            return None
        return m.group(0)

    @classmethod
    def _is_unit_start(cls, line: str) -> bool:
        """True when `line` starts a new clause or numbered section inside a multi-line block."""
        return bool(cls._clause_prefix(line) or cls.RE_SECTION_NUM.match(line) or cls.RE_CHAPTER_TITLE.match(line))

    @classmethod
    def _split_block(cls, text: str) -> List[str]:
        """Split a text block at lines that start a new clause/section so each one is its own node."""
        segments: List[List[str]] = [[]]
        for line in text.split("\n"):
            if segments[-1] and cls._is_unit_start(line.strip()):
                segments.append([])
            segments[-1].append(line)
        return ["\n".join(seg).strip() for seg in segments if "".join(seg).strip()]

    @staticmethod
    def _looks_like_header(cells: List[str]) -> bool:
        return not any(re.search(r"\d", c) for c in cells) and all(len(c) <= 40 for c in cells)

    @classmethod
    def analyze_structure(cls, pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        structured_nodes: List[Dict[str, Any]] = []
        current_chapter = "General Specification"
        current_section = "General Provision"
        current_clause = None

        active_table = None
        prev_headers: Optional[List[str]] = None   # headers of the last table, for headerless continuations
        prev_table_page = 0

        last_table: Optional[Dict[str, Any]] = None   # most recently emitted table node

        def flush_table() -> None:
            nonlocal active_table, last_table
            if active_table:
                if active_table["rows"]:
                    structured_nodes.append(active_table)
                    last_table = active_table
                active_table = None

        for page in pages_data:
            page_no = page["page_no"]
            flush_table()          # a table node never spans pages, so every chunk keeps its own page number
            current_clause = None  # clauses restart at page boundaries

            for block in page["blocks"]:
                raw = block.get("text", "").strip()
                if not raw:
                    continue

                is_table_block = block.get("type") == "table" or (
                    "|" in raw and all("|" in ln for ln in raw.split("\n") if ln.strip()))
                parsed_table = cls._parse_table_block(raw, page_no) if is_table_block else None
                if parsed_table:
                    headers = parsed_table["headers"]
                    cell_rows = [list(r.values()) for r in parsed_table["rows"]]
                    raw_head = parsed_table["raw_headers"]
                    if sum(1 for c in raw_head if c.strip()) < 2 and len(raw_head) > 1:
                        # row 0 is a letterhead/title, not a header: use neutral headers and keep it as data
                        cell_rows.insert(0, list(raw_head))
                        headers = [f"Column {i + 1}" for i in range(len(raw_head))]
                    first_on_page = block is page["blocks"][0] or all(
                        b.get("type") != "text" or not b.get("text", "").strip() for b in page["blocks"][:page["blocks"].index(block)])
                    if (first_on_page and prev_headers and prev_table_page == page_no - 1 and len(headers) == len(prev_headers)
                            and headers != prev_headers
                            and (not parsed_table["raw_headers"][0].strip()
                                 or not cls._looks_like_header(parsed_table["raw_headers"]))):
                        # continuation of a table from the previous page whose header row was not repeated:
                        # what we parsed as the header row is really data
                        cell_rows.insert(0, list(parsed_table["raw_headers"]))
                        headers = prev_headers
                    if active_table and active_table["headers"] != headers:
                        flush_table()
                    if not active_table:
                        active_table = {
                            "type": "table", "chapter": current_chapter, "section": current_section,
                            "clause": current_clause, "headers": headers, "rows": [],
                            "source_pages": [page_no], "page_no": page_no, "text_repr": "",
                        }
                    for cells in cell_rows:
                        row = dict(zip(headers, cells))
                        if not cells[0].strip() and any(c.strip() for c in cells[1:]):
                            # a row whose serial-number cell is empty is the tail of a row split by a page break
                            # (or a merged cell): join it onto the row it belongs to
                            target = active_table["rows"][-1] if active_table["rows"] else (
                                last_table["rows"][-1] if last_table and last_table["page_no"] == page_no - 1
                                and last_table["headers"] == headers and last_table["rows"] else None)
                            if target is not None:
                                for h in headers:
                                    old, frag = target.get(h, ""), row.get(h, "")
                                    if frag and " ".join(old.split()).lower().endswith(" ".join(frag.split()).lower()):
                                        continue          # the PDF already printed this overflow in the first part of the cell
                                    target[h] = " ".join(x for x in (old, frag) if x).strip()
                                if target not in active_table["rows"] and last_table:
                                    last_table["text_repr"] = cls._format_table_text(last_table["headers"], last_table["rows"])
                                continue
                        active_table["rows"].append(row)
                    active_table["text_repr"] = cls._format_table_text(active_table["headers"], active_table["rows"])
                    prev_headers, prev_table_page = headers, page_no
                    continue

                flush_table()
                for idx, text in enumerate(cls._split_block(raw)):
                    first_line = text.split("\n")[0].strip()
                    first_line_lower = first_line.lower()
                    is_heading = bool(block.get("is_heading")) and idx == 0

                    # Ignore address / contact header lines from structure detection
                    is_address = bool(cls._ADDRESS_RE.search(first_line_lower)) and not cls._clause_prefix(first_line)
                    clause_no = None if is_address else cls._clause_prefix(first_line)

                    if cls._TOC_LINE.search(first_line):
                        # a table-of-contents entry ('Annexure 1 ........ 14') is not a chapter of the tender
                        structured_nodes.append({
                            "type": "paragraph", "chapter": current_chapter, "section": current_section,
                            "clause": current_clause, "page_no": page_no, "text": text, "bbox": block.get("bbox")})
                        continue
                    if not is_address and cls.RE_CHAPTER_TITLE.match(first_line):
                        current_chapter, current_section, current_clause = first_line, "General Section", None
                        block_type = "chapter"
                    elif not is_address and (cls.RE_SECTION_NUM.match(first_line) and not clause_no
                                             and first_line.isupper() and len(first_line) < 90
                                             or (is_heading and cls.RE_SECTION_TITLE.match(first_line))):
                        current_section, current_clause = first_line, None
                        block_type = "section"
                    elif (not is_address and first_line.isupper() and len(first_line) < 60
                          and any(w in first_line for w in cls.CHAPTER_WORDS)):
                        current_chapter, current_section, current_clause = first_line, "General Section", None
                        block_type = "chapter"
                    elif clause_no and cls._is_numbered_heading(first_line, text):
                        current_section, current_clause = first_line, None       # '2.11 Eligible Bidders'
                        block_type = "section"
                    elif clause_no:
                        current_clause = clause_no
                        block_type = "clause"
                    elif is_heading:
                        current_section, current_clause = first_line, None
                        block_type = "section"
                    else:
                        block_type = "paragraph"

                    structured_nodes.append({
                        "type": block_type, "chapter": current_chapter, "section": current_section,
                        "clause": current_clause, "page_no": page_no, "text": text, "bbox": block.get("bbox"),
                    })

        flush_table()
        log_pipeline_step("S3_STRUCTURE_ANALYZER", status="SUCCESS", message=f"Analyzed structure into {len(structured_nodes)} nodes")
        return structured_nodes

    @classmethod
    def _parse_table_block(cls, text: str, page_no: int) -> Optional[Dict[str, Any]]:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        table_lines = [l for l in lines if "|" in l]
        if not table_lines or len(table_lines) < 2:
            return None

        def split_row(line: str) -> List[str]:
            parts = [p.strip() for p in line.split("|")]
            if parts and parts[0] == "":
                parts.pop(0)
            if parts and parts[-1] == "":
                parts.pop()
            return parts

        headers = split_row(table_lines[0])
        raw_headers = list(headers)
        seen: Dict[str, int] = {}
        for i, h in enumerate(headers):          # blank/duplicate headers would silently merge columns
            name = h or f"Column {i + 1}"
            seen[name] = seen.get(name, 0) + 1
            headers[i] = name if seen[name] == 1 else f"{name} ({seen[name]})"
        rows = []
        for line in table_lines[1:]:
            cells = split_row(line)
            if cells and all(re.fullmatch(r":?-{3,}:?", c.strip()) for c in cells):
                continue
            if len(cells) < len(headers):                 # a merged / missing cell: keep the row, pad the gap
                cells = cells + [""] * (len(headers) - len(cells))
            elif len(cells) > len(headers):               # an extra cell: fold it into the last column, lose nothing
                cells = cells[:len(headers) - 1] + [" ".join(c for c in cells[len(headers) - 1:] if c)]
            rows.append({headers[i]: cells[i] for i in range(len(headers))})

        if not rows:
            return None

        return {"headers": headers, "raw_headers": raw_headers, "rows": rows}

    @classmethod
    def _format_table_text(cls, headers: List[str], rows: List[Dict[str, str]]) -> str:
        formatted = []
        for r in rows:
            pairs = [f"{h}: {r.get(h, '')}" for h in headers if r.get(h)]
            formatted.append(" | ".join(pairs))
        text = "\n".join(f for f in formatted if f)
        if not text:
            # a blank form (price bid, staff sheet): the column names ARE its content, keep them
            names = [h for h in headers if not re.fullmatch(r"Column \d+(?: \(\d+\))?", h)]
            text = "Blank form with columns: " + " | ".join(names) if names else ""
        return text
