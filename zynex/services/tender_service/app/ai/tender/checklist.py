"""S11 - the full tender checklist: everything a person would list when reading the whole tender.

The eligibility analysis (S5-S10) reads only the eligibility section and compares each requirement with the company records.
This stage reads the WHOLE document, window by window, and lists what the tender asks for in eight groups (eligibility, scope of
work, deliverables, timeline, commercial terms, submission, evaluation, other obligations) so a person can compare it with the
company's own records by hand.

Accuracy rules
  * The model must copy each item word for word. An item whose text cannot be found in the tender is dropped (never kept as a guess).
  * The page number comes from where the text was found, not from what the model says.
  * Nothing here changes the eligibility verdict.
"""
import asyncio
import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

from app.ai.tender import llm_call
from app.ai.tender.json_parse import parse_json_robust
from app.ai.tender.run_options import RunOptions
from app.core.config import settings
from app.schemas.eligibility import ChunkSchema, CriterionSchema
from app.services.eligibility.locator import is_toc
from app.services.eligibility.pipeline_log import log_pipeline_step

CATEGORIES: Dict[str, str] = {
    "eligibility": "Eligibility: what the bidder must be or have (turnover, net worth, years in business, similar past projects, certificates, registrations, staff, not blacklisted, local office)",
    "scope": "Scope of work: what the selected company must build, supply, install, operate, migrate or support",
    "deliverables": "Deliverables: modules, systems, documents, reports, training and milestones to be handed over",
    "timeline": "Timeline: submission and opening dates, bid validity, project duration, go-live, warranty and support periods",
    "commercial": "Commercial terms: EMD or bid security, tender fee, price basis, payment schedule, taxes, performance guarantee, penalties, liquidated damages",
    "submission": "Submission: forms, annexures, declarations and documents to submit, how and where, number of covers, signing, format",
    "evaluation": "Evaluation: how bids are scored or ranked, marks, weightage, minimum technical score, L1 or QCBS rules",
    "obligations": "Other obligations: service levels, warranty, support, security, confidentiality, ownership of code, subcontracting, insurance",
}
LABELS: Dict[str, str] = {
    "eligibility": "Eligibility", "scope": "Scope of work", "deliverables": "Deliverables", "timeline": "Timeline",
    "commercial": "Commercial terms", "submission": "Bid submission", "evaluation": "Evaluation", "obligations": "Other obligations",
}
ORDER = list(CATEGORIES)

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": ORDER}, "text": {"type": "string"}, "page": {"type": "integer"}},
        "required": ["category", "text"]}}},
    "required": ["items"],
}

SYSTEM = (
    "You read a tender (RFP, EOI or bid document) and write the checklist an applicant company needs, so they can compare it with their own company records.\n"
    "List EVERY requirement, condition, obligation, deadline, fee, document to submit and deliverable the text states (for the bidder, applicant, reseller, partner or company, and what the issuer promises to provide), in these groups:\n"
    + "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items()) + "\n\n"
    "RULES:\n"
    "- `text` MUST be copied word for word from the text given (same words, same numbers). Never paraphrase, never summarise, never add anything.\n"
    "- One item per requirement: one sentence or one table row, at most about 60 words. Split a sentence that joins several requirements.\n"
    "- `page` is the page number from the nearest '--- [PAGE n] ---' marker above the text.\n"
    "- Skip headings, page headers and footers, the table of contents, definitions, legal boilerplate that puts no duty on the bidder, and the tender issuer's own internal procedure.\n"
    "- List at most 30 items per answer, the most important first. Never repeat an item.\n"
    "- If the text holds nothing for the checklist, return {\"items\": []}.\n"
    "- The tender may be in any language: copy the text in its own language and script."
)

MAX_ITEM_CHARS = 700
MIN_ITEM_CHARS = 8
_PAGE = re.compile(r"--- \[PAGE (\d+)\] ---")
_BACKOFF_S = (1, 2, 4)
ProgressCb = Callable[[int, int, int], Awaitable[None]]


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", (text or "").lower()).strip()


@dataclass
class _Metrics:
    windows: int = 0
    calls: int = 0
    failed_windows: int = 0
    raw_items: int = 0
    not_found_in_tender: int = 0
    too_short: int = 0
    duplicates: int = 0
    reworded_replaced: int = 0
    swept_by_pattern: int = 0
    empty_retried: int = 0
    kept: int = 0
    pages_skipped: int = 0
    windows_skipped_no_signal: int = 0

    def as_dict(self) -> Dict[str, int]:
        return dict(self.__dict__)


@dataclass
class _Window:
    pages: List[int] = field(default_factory=list)
    text: str = ""


# Strong signs of a requirement: duty words, penalties, amounts, percentages, dates and periods. Background text (company history, product
# description) has almost none; on the pages of real tenders that produced items there were always 3 or more. A long window with fewer
# than STRONG_SIGNALS is not sent to the AI (it answers "nothing" and a retry costs another call). Numbered clauses and fact-table rows
# on it are still swept by pattern, and a short window (under SHORT_WINDOW characters) is asked whenever it has any signal.
_SIGNAL = re.compile(
    r"\b(?:shall|must|should|required|mandatory|liable|penalt\w*|liquidated|non-?refundable|disqualif\w*|reject\w*)\b"
    r"|\b(?:rs\.?|inr)\s*\d|₹|\d\s*%|\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{2,4}|\b\d+\s*(?:days?|weeks?|months?|years?)\b",
    re.IGNORECASE)
STRONG_SIGNALS = 3
SHORT_WINDOW = 1500


def _signals(text: str) -> int:
    return len(_SIGNAL.findall(text or ""))


def _worth_asking(text: str) -> bool:
    n = _signals(text)
    return n >= STRONG_SIGNALS or (n >= 1 and len(text) < SHORT_WINDOW)


_BLANKS = re.compile(r"_{4,}|\.{6,}|\[\s*(?:date|name|amount|___)[^\]]*\]", re.IGNORECASE)


def _is_blank_form(body: str) -> bool:
    """An annexure format with blanks to fill in (letters, declarations, bank guarantee formats): the annexure list names it, the page adds nothing."""
    lines = [l for l in body.split("\n") if l.strip()]
    if len(lines) < 4:
        return False
    blanks = len(_BLANKS.findall(body))
    signoff = bool(re.search(r"signature|authori[sz]ed signatory", body, re.IGNORECASE)) and bool(re.search(r"\bplace\s*:|\bdate\s*:", body, re.IGNORECASE))
    return blanks >= 6 or (blanks >= 3 and signoff)


def _windows(chunks: List[ChunkSchema], limit: int, m: _Metrics) -> Tuple[List[_Window], Dict[int, str]]:
    """Group the readable pages into windows of about `limit` characters; also return each page's text for locating items."""
    page_text: Dict[int, str] = {}
    for c in sorted(chunks, key=lambda c: (c.physical_page, c.chunk_id)):
        body = _PAGE.sub("", c.chunk_text or "").strip()
        page_text[c.physical_page] = (page_text.get(c.physical_page, "") + "\n" + body).strip()
    out: List[_Window] = []
    cur = _Window()
    for page in sorted(page_text):
        body = page_text[page]
        if len(body) < 80 or is_toc(body) or _is_blank_form(body):
            m.pages_skipped += 1
            continue
        block = f"--- [PAGE {page}] ---\n{body}\n"
        if cur.text and len(cur.text) + len(block) > limit:
            out.append(cur)
            cur = _Window()
        cur.pages.append(page)
        cur.text += block
    if cur.text:
        out.append(cur)
    return out, page_text


_SENT_SPLIT = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9(•])|\n+")


def _closest_sentence(item: str, win: _Window, page_text: Dict[int, str]) -> Optional[Tuple[int, str]]:
    """When the model reworded a line, find the tender's own sentence that says the same thing (or None)."""
    needle = _norm(item)
    best: Tuple[float, int, str] = (0.0, 0, "")
    for p in win.pages:
        parts = [x.strip(" |•-") for x in _SENT_SPLIT.split(page_text[p]) if len(x.strip()) >= MIN_ITEM_CHARS]
        # also try each sentence joined with the next one (a requirement that runs over a line break)
        cands = parts + [f"{a} {b}" for a, b in zip(parts, parts[1:])]
        for c in cands:
            cn = _norm(c)
            if not cn or not (0.5 <= len(cn) / max(1, len(needle)) <= 2.2):
                continue
            score = fuzz.token_set_ratio(needle, cn)
            if score > best[0]:
                best = (score, p, c)
    return (best[1], re.sub(r"\s+", " ", best[2]).strip()) if best[0] >= 82 else None


def _locate(item: str, win: _Window, page_text: Dict[int, str]) -> Optional[int]:
    """Page where `item` really occurs (word for word, ignoring punctuation and spacing), or None."""
    needle = _norm(item)
    if len(needle) < MIN_ITEM_CHARS:
        return None
    for p in win.pages:
        if needle in _norm(page_text[p]):
            return p
    # a table row or a sentence the model joined across a line break: accept a near-exact match on one page only
    best_page, best = None, 0.0
    for p in win.pages:
        score = fuzz.partial_ratio(needle, _norm(page_text[p])) if len(needle) <= 400 else 0.0
        if score > best:
            best_page, best = p, score
    return best_page if best >= 96 else None


_CLAUSE_START = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(?=\S)")
_CLAUSE_KEYS = re.compile(r"\b(?:shall|must|required|should|liable|within|every|valid(?:ity)?|fee|rs\.?|inr|cost|payment|paid|submit|submission|"
                          r"deliver|provide[d]?|eligible|only if|non-?refundable|terminat|reject|final|borne|charge)\b|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", re.IGNORECASE)
_CAT_RULES = [("timeline", r"\b(?:date|days|months?|years?|validity|valid for|period|within|every)\b"),
              ("commercial", r"\b(?:fee|rs\.?|inr|cost|payment|paid|charge|price|tax|refund)\b"),
              ("submission", r"\b(?:submit|submission|annexure|documents?|sign(?:ed)?|template|format)\b"),
              ("deliverables", r"\b(?:deliverables?|training|manual|brochure|certificate shall)\b"),
              ("eligibility", r"\b(?:eligible|who can apply|msmes?|start ?ups?|registered in|incorporated)\b")]


def _numbered_clauses(text: str) -> List[str]:
    """Numbered clauses ('5.4. This invitation ... 31/12/2026') of one page, each joined across its line breaks."""
    out: List[str] = []
    cur: List[str] = []
    for line in text.split("\n"):
        if _CLAUSE_START.match(line):
            if cur:
                out.append(" ".join(cur))
            cur = [line.strip()]
        elif cur and line.strip() and not line.startswith("[TABLE"):
            cur.append(line.strip())
        elif not line.strip() and cur:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return [re.sub(r"\s+", " ", c).strip() for c in out]


_ROW_VALUE = re.compile(r"\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{4}|\b(?:rs\.?|inr|₹)\s*\d|\d\s*%|\b\d+\s*(?:days?|months?|years?|hours?|lakhs?|crores?)\b", re.IGNORECASE)
_SERIAL_LABEL = re.compile(r"^(?:s\.?\s*no\.?|sl\.?\s*no\.?|sr\.?\s*no\.?|no\.?|#|column\s*\d+)$", re.IGNORECASE)


def _table_rows_with_values(text: str) -> List[str]:
    """Fact-sheet rows like 'S.No.: 10 | Information: Last date for submission of bids | Details: 28/09/2026 till 04:00 PM' -> 'Last date for
    submission of bids: 28/09/2026 till 04:00 PM' (cells joined, nothing added). Only rows that carry a date, amount, percentage or period."""
    out: List[str] = []
    for line in text.split("\n"):
        if " | " not in line or ":" not in line:
            continue
        cells = [(l.strip(), v.strip()) for l, _sep, v in (c.partition(": ") for c in line.split(" | ")) if v.strip()]
        cells = [(l, v) for l, v in cells if not _SERIAL_LABEL.match(l)]
        if len(cells) < 2 or not _ROW_VALUE.search(" ".join(v for _l, v in cells[1:])):
            continue
        out.append(f"{cells[0][1]}: " + "; ".join(v for _l, v in cells[1:]))
    return out


def _sweep_missed_clauses(page_text: Dict[int, str], found: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Safety net: a numbered clause that states a duty, date, fee or limit but is not covered by any item the AI listed on that page
    is added word for word and marked as found by pattern. The AI sometimes answers 'nothing' for a page that is full of clauses."""
    added: List[Dict[str, Any]] = []
    for page, text in sorted(page_text.items()):
        have = [_norm(i["text"]) for i in found + added if i["page"] == page]
        for clause in _numbered_clauses(text):
            body = _CLAUSE_START.sub("", clause, count=1).strip()
            if len(_norm(body).split()) < 6 or not _CLAUSE_KEYS.search(body):
                continue
            nb = _norm(body)
            if any(h and (h in nb or nb in h or fuzz.partial_ratio(h[:200], nb) >= 85) for h in have):
                continue
            cat = next((c for c, rx in _CAT_RULES if re.search(rx, body, re.IGNORECASE)), "obligations")
            added.append({"category": cat, "text": body[:MAX_ITEM_CHARS], "page": page, "found_by": "pattern"})
            have.append(nb)
        for row in _table_rows_with_values(text):
            nr = _norm(row)
            if len(nr.split()) < 3 or any(h and (h in nr or nr in h or fuzz.partial_ratio(h[:200], nr) >= 85) for h in have):
                continue
            cat = next((c for c, rx in _CAT_RULES if re.search(rx, row, re.IGNORECASE)), "obligations")
            added.append({"category": cat, "text": row[:MAX_ITEM_CHARS], "page": page, "found_by": "pattern"})
            have.append(nr)
    return added


async def _ask(window: _Window, options: Optional[RunOptions], m: _Metrics, retry_empty: bool = False) -> Optional[List[dict]]:
    attempts = max(1, settings.ELIGIBILITY_MAX_ATTEMPTS)
    for attempt in range(1, attempts + 1) if retry_empty else range(attempts):
        m.calls += 1
        try:
            user = window.text if not retry_empty else (
                window.text + "\n\nThis text does contain conditions, dates, fees or obligations. List them as {\"items\": [...]}, copying each word for word.")
            content = await llm_call.chat_json(SYSTEM, user, SCHEMA, attempt=attempt, options=options, max_tokens=3000)
            parsed = parse_json_robust(content, required_key="text")
            items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
            return [p for p in items if isinstance(p, dict)]
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log_pipeline_step("S11_CHECKLIST", page_no=window.pages[0], status="ATTEMPT_FAILED",
                              message=f"attempt {attempt + 1}/{attempts}: {type(e).__name__}: {e}")
            if attempt < attempts - 1:
                await asyncio.sleep(_BACKOFF_S[min(attempt, len(_BACKOFF_S) - 1)])
    return None


async def extract_checklist(chunks: List[ChunkSchema], options: Optional[RunOptions] = None,
                            on_progress: Optional[ProgressCb] = None) -> Dict[str, Any]:
    m = _Metrics()
    if settings.CHECKLIST_MODEL:
        options = dataclasses.replace(options or RunOptions(), model=settings.CHECKLIST_MODEL)
    wins, page_text = _windows(chunks, int(settings.CHECKLIST_WINDOW_CHARS or 5500), m)
    m.windows = len(wins)
    found: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    seen: List[Tuple[str, str]] = []

    async def read(win: _Window) -> Optional[List[dict]]:
        """One window: ask the AI; an empty answer on a window full of duties is asked once more (a model slip, not an empty page)."""
        if not _worth_asking(win.text):
            m.windows_skipped_no_signal += 1
            return []
        items = await _ask(win, options, m)
        if items == [] and _signals(win.text) >= STRONG_SIGNALS:
            m.empty_retried += 1
            items = await _ask(win, options, m, retry_empty=True)
        return items

    # windows are independent, so they are asked together up to the AI concurrency (1 = one after the other); results are
    # handled in page order afterwards, so the checklist is the same whatever the speed
    gate = asyncio.Semaphore(max(1, int(getattr(settings, "LLM_CONCURRENCY", 1) or 1)))
    done = 0

    async def guarded(win: _Window) -> Optional[List[dict]]:
        nonlocal done
        async with gate:
            if on_progress:
                await on_progress(done, len(wins), len(found))
            res = await read(win)
        done += 1
        return res

    results = await asyncio.gather(*(guarded(w) for w in wins))
    for win, items in zip(wins, results):
        if items is None:
            m.failed_windows += 1
            continue
        for raw in items:
            text = re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()
            cat = str(raw.get("category") or "").strip().lower()
            m.raw_items += 1
            if cat not in CATEGORIES:
                cat = "obligations"
            if len(_norm(text)) < MIN_ITEM_CHARS or len(_norm(text).split()) < 2:
                m.too_short += 1
                dropped.append({"category": cat, "text": text, "reason": "too short"})
                continue
            page = _locate(text[:MAX_ITEM_CHARS], win, page_text)
            approx = False
            if page is None:
                near = _closest_sentence(text, win, page_text)
                if near:                        # keep the TENDER's wording, never the model's
                    page, text, approx = near[0], near[1], True
                    m.reworded_replaced += 1
            if page is None:
                m.not_found_in_tender += 1
                dropped.append({"category": cat, "text": text, "reason": "NOT FOUND WORD FOR WORD IN THE TENDER"})
                continue
            key = _norm(text)
            if any(c == cat and (k == key or fuzz.ratio(k, key) >= 94) for c, k in seen):
                m.duplicates += 1
                dropped.append({"category": cat, "text": text, "reason": "duplicate"})
                continue
            seen.append((cat, key))
            found.append({"category": cat, "text": text[:MAX_ITEM_CHARS], "page": page, **({"closest_wording": True} if approx else {})})
    if on_progress:
        await on_progress(len(wins), len(wins), len(found))
    swept = _sweep_missed_clauses(page_text, found)
    m.swept_by_pattern = len(swept)
    found += swept
    found.sort(key=lambda x: (x["page"], ORDER.index(x["category"])))
    for n, it in enumerate(found, start=1):
        it["id"] = f"K{n:03d}"
    m.kept = len(found)
    return {"items": found, "metrics": m.as_dict(), "labels": LABELS, "dropped": dropped}


def mark_compared(items: List[Dict[str, Any]], criteria: List[CriterionSchema]) -> int:
    """Flag the eligibility items that the eligibility analysis already compared with the company records."""
    quotes = [_norm(c.source_text) for c in criteria if c.source_text]
    n = 0
    for it in items:
        it["compared"] = False
        if it["category"] != "eligibility":
            continue
        t = _norm(it["text"])
        if any(q and (q in t or t in q or fuzz.partial_ratio(q, t) >= 88) for q in quotes):
            it["compared"] = True
            n += 1
    return n
