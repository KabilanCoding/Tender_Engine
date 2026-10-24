"""S6 - LLM extraction of eligibility criteria from tender chunks.

Provider-agnostic (Ollama or NVIDIA via llm_client). Holds no module-level mutable state:
metrics live on a per-run object so concurrent runs cannot corrupt each other.
"""
import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from app.ai import cloud_clients
from app.ai.tender import llm_call
from app.ai.tender.json_parse import parse_json_robust
from app.ai.tender.run_options import RunOptions
from app.ai.tender.prompts import (
    EXTRACTION_JSON_SCHEMA,
    TABLE_JSON_SCHEMA,
    build_extraction_user_prompt,
    build_table_user_prompt,
    extraction_system_prompt,
    table_system_prompt,
)
from app.core.config import settings
from app.schemas.eligibility import ChunkSchema, CriterionSchema
from app.schemas.field_ontology import canonicalize_field
from app.services.eligibility.multilingual import is_latin
from app.services.eligibility.normalizer import Normalizer
from app.services.eligibility.operators import canonical_operator
from app.services.eligibility.pipeline_log import log_pipeline_step
from app.services.eligibility.locator import (block_is_eligibility, find_core_chunks, is_toc, row_cells,
                                                    table_blocks)
from app.services.eligibility.prefilter import STRONG_SCORE, select_chunks
from app.services.eligibility import trace
from app.services.eligibility.groups import GroupIndex

ProgressCb = Callable[[int, int, int, int], Awaitable[None]]
_BACKOFF_S = (1, 2, 4, 8)
_NULLISH = {"N/A", "NONE", "NULL", ""}
_GENERIC_COLUMN = re.compile(r"^\s*column\s*\d+\s*$", re.IGNORECASE)
_SERIAL = re.compile(r"^(?:s\.?\s*no\.?|sl\.?\s*no\.?|sr\.?\s*no\.?|no\.?|#|serial.*|column \d+|page\s*(?:no\.?|number)?|"
                     r"annexure.*|ref(?:erence)?\.?)$", re.IGNORECASE)
_SUBHEADING = re.compile(r"(?:criteria|requirements?|conditions?|details|qualification|eligibility|experience|capability)\W*$", re.IGNORECASE)
_PROOF = re.compile(r"proof|document|evidence|supporting|enclos|to be submitted", re.IGNORECASE)
_OPTIONAL = re.compile(r"\b(?:optional|preferred|desirable|if available)\b", re.IGNORECASE)
_MANDATORY = re.compile(r"\b(?:shall|must|should|required|mandatory)\b", re.IGNORECASE)
_NUMERIC_FIELDS = {"annual_turnover", "net_worth", "working_capital", "project_value", "similar_work_value",
                   "software_component_value", "experience_years", "contract_count", "team_role_count",
                   "bid_validity_days", "emd_amount", "tender_fee"}
_COMPARISONS = {">=", "<=", ">", "<", "==", "!="}
_PEOPLE_WORDS = re.compile(r"\b(?:team|personnel|staff|key\s+(?:person|position|expert|resource)s?|manpower|resource persons?|engineers?|(?:software|senior|junior|java|web|mobile|full[- ]stack)\s+developers?|architects?|managers?|experts?|employees?|professionals?|cv|resume)\b", re.IGNORECASE)
_FEE_ROW = re.compile(r"\b(?:emd|earnest\s+money|bid\s+security|(?:rfp|tender|bid)\s+document\s+fee|tender\s+fee|rfp\s+fee)\b", re.IGNORECASE)
_SCORING_QUOTE = re.compile(r"\b\d+\s*marks?\b|\bmarks?\s*[:=\-]?\s*\d+|\bmaximum\s+(?:marks|score)\b|\bweightage\b|\bscoring\b", re.IGNORECASE)
_FORM_ENTRY = re.compile(r"^\W*(?:form|annexure|appendix|format|schedule)[\s\-]*(?:no\.?\s*)?\d+\b", re.IGNORECASE)
_DECLARATION = re.compile(r"^\W*(?:i|we|i\s*/\s*we)\b.{0,200}?\b(?:hereby|confirm|declare|certify|undertake|agree|shall not|have read)\b", re.IGNORECASE | re.DOTALL)
_DOCUMENT_WORDS = re.compile(r"\b(?:submit|submitted|enclose|enclosed|attach|attached|furnish|declaration|undertaking|affidavit|letter|certificate|form|annexure|copy|copies|statement)\b", re.IGNORECASE)
_DOCUMENT_FIELDS = {"bidder_particulars", "cover_letter", "work_order_copy", "audited_balance_sheet", "income_tax_returns",
                    "ca_turnover_certificate", "certificate_of_incorporation", "non_blacklisting_declaration",
                    "letter_of_authorization", "manpower_resume_required", "tn_office_proof", "performance_certificate",
                    "completion_certificate", "solvency_certificate_val"}
_EXPERIENCE_WORDS = re.compile(r"experience|existence|existing|in business|operation|years of (?:business|operat)", re.IGNORECASE)
TABLE_BATCH_ROWS = 8
FALLBACK_MAX_PAGES = 12   # pages read when the located eligibility section yields no criteria
PROSE_MIN_CHARS = 600   # prose outside tables on an eligibility page worth its own AI call


@dataclass
class ExtractionMetrics:
    total_chunks: int = 0
    candidate_chunks: int = 0
    filtered_chunks: int = 0
    prefiltered_chunks: int = 0
    filter_reasons: Dict[str, int] = field(default_factory=dict)
    core_chunks: int = 0
    extra_chunks: int = 0
    table_rows: int = 0
    rows_retried: int = 0
    rows_unresolved: int = 0
    chunks_successful: int = 0
    chunks_failed: int = 0
    chunks_with_retry: int = 0
    total_attempts: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    retry_count: int = 0
    completed_chunks: int = 0
    live_criteria: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_chunks": self.total_chunks,
            "llm_candidate_chunks": self.candidate_chunks,
            "chunks_successful": self.chunks_successful,
            "chunks_failed": self.chunks_failed,
            "chunks_with_retry": self.chunks_with_retry,
            "filtered_chunks": self.filtered_chunks,
            "prefiltered_chunks": self.prefiltered_chunks,
            "filter_reasons": self.filter_reasons,
            "core_chunks": self.core_chunks,
            "extra_chunks": self.extra_chunks,
            "table_rows": self.table_rows,
            "rows_retried": self.rows_retried,
            "rows_unresolved": self.rows_unresolved,
            "actual_llm_api_calls": self.total_attempts,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "retry_count": self.retry_count,
            "configured_concurrency": settings.LLM_CONCURRENCY,
            "provider": cloud_clients.effective_provider(),
        }


class CriteriaExtractor:
    MIN_CHUNK_CHARS = 30

    def __init__(self, options: Optional[RunOptions] = None):
        self.options = options or RunOptions()
        self._allowed_blocks: Dict[str, List[List[str]]] = {}   # chunk id -> table blocks that hold eligibility rows
        self._core_ids: set = set()                              # chunk ids of the located eligibility section
        self._groups = GroupIndex([])                            # bidder categories, rebuilt for each document in extract()
        self.plan_info: Dict[str, Any] = {}                      # what S5 decided to read, for the stage artifact

    @staticmethod
    def _outside_tables(chunk_text: str) -> str:
        """Prose of a page without its tables and page marker."""
        body = re.sub(r"\[TABLE START\].*?(?:\[TABLE END\]|\Z)", "", chunk_text, flags=re.DOTALL)
        body = re.sub(r"^.*?\[TABLE END\]", "", body, count=1, flags=re.DOTALL) if "[TABLE END]" in body else body
        return re.sub(r"--- \[PAGE \d+\] ---", "", body).strip()

    @classmethod
    def should_process_chunk(cls, chunk: ChunkSchema) -> Tuple[bool, str]:
        text = chunk.chunk_text.strip()
        if not text or chunk.char_count == 0:
            return False, "EMPTY_NOISE_SKIP"
        if is_toc(text) or re.search(r"\.{4,}\s*\d+", text) or re.match(r"(?:--- \[PAGE \d+\] ---\s*)?table of contents", text, re.IGNORECASE):
            return False, "TABLE_OF_CONTENTS_SKIP"
        if chunk.content_type in ("table", "clause", "section"):
            return True, "STRUCTURAL_CHUNK"
        if chunk.char_count >= cls.MIN_CHUNK_CHARS:
            return True, "NARRATIVE_CHUNK"
        return False, "TOO_SHORT_SKIP"

    @staticmethod
    def _prefilter(candidates: List[ChunkSchema], m: "ExtractionMetrics") -> List[ChunkSchema]:
        """On large tenders keep only eligibility-looking chunks (see services.eligibility.prefilter)."""
        if not settings.ELIGIBILITY_PREFILTER or len(candidates) < settings.ELIGIBILITY_PREFILTER_MIN_CHUNKS:
            return candidates
        keep, _scores = select_chunks(candidates, settings.ELIGIBILITY_PREFILTER_MAX_FRACTION)
        kept = [c for c in candidates if c.chunk_id in keep]
        skipped = len(candidates) - len(kept)
        if skipped:
            m.filtered_chunks += skipped
            m.prefiltered_chunks = skipped
            m.filter_reasons["LOW_ELIGIBILITY_SIGNAL"] = skipped
            log_pipeline_step("S6_LLM_EXTRACTOR", status="PREFILTER",
                              message=f"kept {len(kept)} of {len(candidates)} chunks with eligibility vocabulary")
        return kept

    def _plan(self, candidates: List[ChunkSchema], m: "ExtractionMetrics") -> List[Tuple[ChunkSchema, str]]:
        """Decide which pages the AI reads and how: eligibility-section tables row by row, prose page by page.

        With a clearly marked eligibility section only those pages (plus a few strongly eligibility-looking
        extras) are read. Without one, fall back to the vocabulary prefilter.
        """
        core = find_core_chunks(candidates) if settings.ELIGIBILITY_PREFILTER else []
        if not core:
            work = [(c, "prose") for c in self._prefilter(candidates, m)]
            self.plan_info = {"mode": "vocabulary prefilter (no clear eligibility section found)",
                              "pages_read": sorted({c.physical_page for c, _ in work}),
                              "pages_skipped": len(candidates) - len({c.chunk_id for c, _ in work})}
            return work

        core_ids = {c.chunk_id for c in core}
        work: List[Tuple[ChunkSchema, str]] = []
        for c in core:
            blocks = table_blocks(c.chunk_text)
            eligible = [b for b in blocks if block_is_eligibility(b)]
            use = eligible or blocks if c.chunk_id in core_ids else blocks
            if use:
                self._allowed_blocks[c.chunk_id] = use
                work.append((c, "table"))
            outside = self._outside_tables(c.chunk_text)
            if not use or len(outside) > PROSE_MIN_CHARS or (len(outside) > 120 and _MANDATORY.search(outside)):
                work.append((c, "prose"))
        m.core_chunks = len(core_ids)
        self._core_ids = core_ids

        rest = [c for c in candidates if c.chunk_id not in core_ids]
        budget = max(0, int(settings.ELIGIBILITY_EXTRA_PAGES))
        if budget and rest:
            _keep, scores = select_chunks(rest, 1.0)
            extras = sorted((c for c in rest if scores[c.chunk_id] >= STRONG_SCORE),
                            key=lambda c: (-scores[c.chunk_id], c.physical_page))[:budget]
            work += [(c, "prose") for c in sorted(extras, key=lambda c: c.physical_page)]
            m.extra_chunks = len(extras)
        _all, all_scores = select_chunks(rest, 1.0) if rest else (set(), {})
        read_extra = {c.chunk_id for c, _ in work} - core_ids
        unread = sorted({c.physical_page for c in rest if all_scores.get(c.chunk_id, 0) >= STRONG_SCORE
                         and c.chunk_id not in read_extra})
        self.plan_info = {
            "mode": "eligibility section located",
            "section_pages": sorted({c.physical_page for c in core}),
            "extra_pages_read": sorted({c.physical_page for c, _ in work if c.chunk_id in read_extra}),
            "table_rows": sum(len(self._table_rows(c, self._allowed_blocks.get(c.chunk_id))) for c, k in work if k == "table"),
            "pages_skipped": len(candidates) - len(core_ids) - m.extra_chunks,
            # pages that read like eligibility text but were left out by the extra-pages limit: an auditor should look
            "unread_pages_with_eligibility_wording": unread[:30],
        }
        skipped = len(candidates) - len(core_ids) - m.extra_chunks
        if skipped > 0:
            m.filtered_chunks += skipped
            m.prefiltered_chunks = skipped
            m.filter_reasons["OUTSIDE_ELIGIBILITY_SECTION"] = skipped
        return work

    @staticmethod
    def _table_rows(chunk: ChunkSchema, allowed: Optional[List[List[str]]] = None) -> List[Tuple[str, str]]:
        """[(condition text, verbatim quote)] for every real row of the eligibility tables of the chunk."""
        blocks = allowed if allowed is not None else table_blocks(chunk.chunk_text)
        rows: List[Tuple[str, str]] = []
        for block in blocks:
            for line in block:
                cells = [(l, v) for l, v in row_cells(line) if v]

                def is_serial(label: str, value: str) -> bool:
                    if _GENERIC_COLUMN.match(label):          # a headerless table: only a short cell ('a.', '3') is a serial
                        return len(value) <= 5
                    return bool(_SERIAL.match(label))
                cond = [(l, v) for l, v in cells if not is_serial(l, v) and not _PROOF.search(l)]
                proof = [(l, v) for l, v in cells if not is_serial(l, v) and _PROOF.search(l)]
                if not cond or all(len(v) < 6 or re.fullmatch(r"[\d\s.,/]+|yes|no|y|n|na|n/a", v, re.I) for _l, v in cond):
                    cond = proof or [(l, v) for l, v in cells if not is_serial(l, v)]   # document-checklist tables
                if not cond:
                    continue
                text = " | ".join(v for _l, v in cond)
                bare = re.sub(r"^\W*\d+(?:\.\d+)*\.?\s+", "", text)           # '5.0 Qualification Criteria' -> the title
                if (len(cond) == 1 and len(bare) < 45 and not re.search(r"\d", bare) and not _MANDATORY.search(bare)
                        and (_SUBHEADING.search(bare) or bare.isupper() or re.fullmatch(r"(?:[A-Z][\w&/-]*\s*){1,4}", bare))):
                    continue                          # a sub-heading row ('Technical Criteria'), not a condition
                quote = max((v for _l, v in cond), key=len)
                rows.append((text, quote))
        return rows

    _COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    _PROJECT_COUNT = re.compile(
        r"\b(?:minimum(?:\s+of)?|at\s+least|not\s+less\s+than)\s+(\d+|" + "|".join(_COUNT_WORDS) + r")\s*(?:\(\s*\w+\s*\)\s*)?"
        r"(?:(?:successfully\s+)?(?:completed|executed|similar|relevant|ongoing|major|work|project|assignment)\s+)*"
        r"(?:[\w/&\-(), ]{0,140}?)\b(?:projects?|works?|assignments?|orders?|contracts?|implementations?)\b", re.IGNORECASE)
    _HAS_EXECUTED = re.compile(r"\b(?:should|must|shall)\s+have\s+(?:successfully\s+)?(?:executed|completed|implemented|delivered)\s+"
                               r"(?:a|an|one|at\s+least\s+one)?\s*(?:single\s+)?(?:similar\s+)?(?:project|work|order|assignment)", re.IGNORECASE)

    @classmethod
    def _project_count_from(cls, text: str) -> Optional[int]:
        m = cls._PROJECT_COUNT.search(text)
        if m:
            raw = m.group(1).lower()
            return int(raw) if raw.isdigit() else cls._COUNT_WORDS[raw]
        return 1 if cls._HAS_EXECUTED.search(text) else None

    @staticmethod
    def _clean_row_items(row_text: str, items: List[dict]) -> List[dict]:
        """Drop model output that is demonstrably wrong for the row, using only the row's own text.

        - a numeric field (turnover, project value, ...) must be compared with a number, not a list/word
        - `experience_years` needs the row to speak of experience/existence (a 'last 3 years' window is not one)
        - exact duplicates inside the row collapse
        """
        out: List[dict] = []
        seen = set()
        for it in items:
            field_id = canonicalize_field(str(it.get("field") or "other").strip())
            op = canonical_operator(it.get("operator"), it.get("value"))
            value = it.get("value")
            if (field_id in {"annual_turnover", "net_worth", "working_capital", "project_value", "similar_work_value"}
                    and isinstance(value, (int, float)) and not isinstance(value, bool)
                    and re.search(rf"\b{re.escape(str(int(value)) if float(value).is_integer() else str(value))}\s*(?:crores?|cr|lakhs?|lacs?)\b",
                                  row_text, re.IGNORECASE)):
                unit = re.search(rf"\b{re.escape(str(int(value)) if float(value).is_integer() else str(value))}\s*(crores?|cr|lakhs?|lacs?)\b",
                                 row_text, re.IGNORECASE).group(1)
                value = f"{value:g} {unit}"            # a bare 50 for 'Rs. 50 Lakhs' would lose the unit
                it = {**it, "value": value}
            if field_id == "net_worth" and op == ">=" and str(value).strip() in ("0", "0.0") and re.search(r"\bpositive\b", row_text, re.I):
                op = ">"                              # 'positive net worth' means above zero, not zero or more
            it = {**it, "field": field_id, "operator": op}
            if field_id in _NUMERIC_FIELDS and (op not in _COMPARISONS or Normalizer.parse_numeric(value) is None):
                continue
            if field_id == "other" and not any(i.get("field") in ("contract_count", "similar_work_value") for i in items):
                n = CriteriaExtractor._project_count_from(row_text)
                if n is not None:                     # 'minimum 3 completed projects' is a count, not free text
                    it = {**it, "field": "contract_count", "operator": ">=", "value": str(n)}
                    field_id, op, value = "contract_count", ">=", str(n)
            if field_id == "experience_years" and is_latin(row_text) and not _EXPERIENCE_WORDS.search(row_text):
                continue
            if field_id in _DOCUMENT_FIELDS and op != "SUBMITTED" and is_latin(row_text) and not _DOCUMENT_WORDS.search(row_text):
                continue                      # a 'document' field on a row that asks for no document is a mis-filing
            if field_id.startswith(("role_", "team_")) and is_latin(row_text) and not _PEOPLE_WORDS.search(row_text):
                continue                      # 'experience in ERP solutions' is not about a team member's role
            key = (field_id, op, str(value).strip().lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    async def _call_rows(self, rows: List[Tuple[int, str]], m: "ExtractionMetrics") -> Dict[int, List[dict]]:
        """One AI call for numbered rows -> {row number: [raw criteria]}. Raises when every attempt fails."""
        attempts = max(1, settings.ELIGIBILITY_MAX_ATTEMPTS)
        last_err: Optional[Exception] = None
        for attempt in range(attempts):
            m.total_attempts += 1
            if attempt:
                m.retry_count += 1
            try:
                content = await llm_call.chat_json(
                    table_system_prompt(self.options.instructions), build_table_user_prompt(rows),
                    TABLE_JSON_SCHEMA, attempt=attempt, options=self.options,
                )
                parsed = parse_json_robust(content, required_key="field")
                m.successful_calls += 1
                items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
                out: Dict[int, List[dict]] = {}
                for it in items:
                    try:
                        out.setdefault(int(it.get("row")), []).append(it)
                    except (TypeError, ValueError, AttributeError):
                        continue
                return out
            except Exception as e:
                m.failed_calls += 1
                last_err = e
                log_pipeline_step("S6_LLM_EXTRACTOR", status="ATTEMPT_FAILED",
                                  message=f"table attempt {attempt + 1}/{attempts}: {type(e).__name__}: {e}")
                if attempt < attempts - 1:
                    await asyncio.sleep(_BACKOFF_S[min(attempt, len(_BACKOFF_S) - 1)])
        raise last_err if last_err else RuntimeError("table extraction failed")

    async def _extract_table_chunk(self, chunk: ChunkSchema, m: "ExtractionMetrics") -> Tuple[List[dict], int, bool]:
        """Every table row becomes at least one checklist item; rows the model skips are retried, then kept
        as 'needs review' so no tender condition silently disappears (even when the model fails entirely)."""
        rows = self._table_rows(chunk, self._allowed_blocks.get(chunk.chunk_id))
        m.table_rows += len(rows)
        quote_of = {i: q for i, (_t, q) in enumerate(rows, 1)}
        text_of = {i: t for i, (t, _q) in enumerate(rows, 1)}
        found: Dict[int, List[dict]] = {}
        start_attempts = m.total_attempts
        batches = [list(range(i + 1, min(i + TABLE_BATCH_ROWS, len(rows)) + 1)) for i in range(0, len(rows), TABLE_BATCH_ROWS)]

        async def _batch(ids: List[int]):
            return await self._call_rows([(n, text_of[n]) for n in ids], m)

        # batches of one page run together; the global LLM concurrency cap still applies
        results = await asyncio.gather(*[_batch(ids) for ids in batches], return_exceptions=True)
        failed_batches = 0
        for ids, got in zip(batches, results):
            if isinstance(got, Exception):
                failed_batches += 1
                continue
            if got and not (set(got) & set(ids)) and set(got) <= set(range(1, len(ids) + 1)):
                got = {ids[0] + k - 1: v for k, v in got.items()}      # the model restarted numbering at 1
            for n, items in got.items():
                if n in ids:                                            # ignore numbers outside this batch
                    found.setdefault(n, []).extend(items)
        if failed_batches == 0:
            missing = [n for n in text_of if n not in found]           # rows the model skipped: ask again, alone
            m.rows_retried += len(missing)

            async def _single(n: int):
                try:
                    return n, (await self._call_rows([(1, text_of[n])], m)).get(1, [])
                except Exception:
                    return n, []
            for n, items in await asyncio.gather(*[_single(n) for n in missing]):
                if items:
                    found[n] = items
        raw: List[dict] = []
        for n in text_of:
            mandatory = not (_OPTIONAL.search(text_of[n]) and not _MANDATORY.search(text_of[n]))
            items = self._clean_row_items(text_of[n], found.get(n) or [])
            if not items and _FEE_ROW.search(text_of[n]):
                kind = "emd_amount" if re.search(r"\bemd\b|earnest|bid\s+security", text_of[n], re.I) else "tender_fee"
                items = [{"field": kind, "operator": "==", "value": text_of[n]}]       # procedural: informational
            if not items:
                count = self._project_count_from(text_of[n])
                if count is not None:                  # the model said nothing, but the row itself states a project count
                    items = [{"field": "contract_count", "operator": ">=", "value": str(count)}]
                else:
                    m.rows_unresolved += 1
                    items = [{"field": "other", "operator": "==", "value": text_of[n]}]
            for it in items:
                raw.append({**it, "source_text": quote_of[n], "mandatory": mandatory})
        return raw, m.total_attempts - start_attempts, failed_batches > 0

    def _trace_plan(self, chunks: List[ChunkSchema], skip_reason: Dict[str, str], work: List[Tuple[ChunkSchema, str]]) -> None:
        """Temporary: record for every chunk whether the AI reads it for eligibility, and why not (see services.eligibility.trace)."""
        if not trace.get():
            return
        kinds: Dict[str, List[str]] = {}
        for c, k in work:
            kinds.setdefault(c.chunk_id, []).append(k)
        rows, pages = [], {}
        for c in chunks:
            if c.chunk_id in skip_reason:
                d = f"SKIPPED: {skip_reason[c.chunk_id]}"
            elif c.chunk_id in kinds:
                d = "READ by the AI (" + " + ".join(kinds[c.chunk_id]) + ")"
            else:
                d = "NOT READ for eligibility: outside the eligibility section (the full checklist reads it separately)"
            rows.append(f"chunk {c.chunk_id} | page {c.physical_page} | {d}")
            pages[c.physical_page] = d if c.physical_page not in pages or d.startswith("READ") else pages[c.physical_page]
        trace.read_or_skipped(rows, self.plan_info, pages)

    def plan_only(self, chunks: List[ChunkSchema]) -> List[Tuple[ChunkSchema, str]]:
        """The pages the AI would read for eligibility, without calling the AI (used by the trace script)."""
        m = ExtractionMetrics(total_chunks=len(chunks))
        candidates: List[ChunkSchema] = []
        skip_reason: Dict[str, str] = {}
        for c in chunks:
            ok, reason = self.should_process_chunk(c)
            if ok:
                candidates.append(c)
            else:
                skip_reason[c.chunk_id] = reason
        work = self._plan(candidates, m)
        self._trace_plan(chunks, skip_reason, work)
        return work

    async def extract(
        self, chunks: List[ChunkSchema], on_progress: Optional[ProgressCb] = None
    ) -> Tuple[List[CriterionSchema], Dict[str, Any]]:
        m = ExtractionMetrics(total_chunks=len(chunks))
        self._groups = GroupIndex(chunks)
        candidates: List[ChunkSchema] = []
        skip_reason: Dict[str, str] = {}
        for c in chunks:
            ok, reason = self.should_process_chunk(c)
            if ok:
                candidates.append(c)
            else:
                skip_reason[c.chunk_id] = reason
                m.filtered_chunks += 1
                m.filter_reasons[reason] = m.filter_reasons.get(reason, 0) + 1
        work = self._plan(candidates, m)
        m.candidate_chunks = len(work)
        self._trace_plan(chunks, skip_reason, work)
        log_pipeline_step("S6_LLM_EXTRACTOR", status="STARTED",
                          message=f"{len(work)} AI calls planned ({m.core_chunks} eligibility-section pages, "
                                  f"{m.extra_chunks} extra) from {len(chunks)} pages, provider {cloud_clients.effective_provider()}")

        if on_progress and work:       # show the real job count right away (not the page count) while the first call runs
            try:
                await on_progress(0, len(work), 0, 0)
            except Exception:
                pass

        lock = asyncio.Lock()

        async def _run(chunk: ChunkSchema, kind: str):
            result = await (self._extract_table_chunk(chunk, m) if kind == "table"
                            else self._extract_chunk(chunk, m))
            async with lock:
                m.completed_chunks += 1
                m.live_criteria += len(result[0])
                snapshot = (m.completed_chunks, m.candidate_chunks, m.successful_calls + m.failed_calls, m.live_criteria)
            if on_progress:
                try:
                    await on_progress(*snapshot)
                except Exception:
                    pass
            return result

        criteria: List[CriterionSchema] = []

        async def _process(jobs: List[Tuple[ChunkSchema, str]]) -> None:
            results = await asyncio.gather(*[_run(c, kind) for c, kind in jobs], return_exceptions=True)
            for (chunk, _kind), res in zip(jobs, results):
                if isinstance(res, Exception):
                    m.chunks_failed += 1
                    log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                                      status="EXTRACTION_FAILED", message=f"{type(res).__name__}: {res}")
                    continue
                raw_items, attempts, exhausted = res
                m.chunks_with_retry += 1 if attempts > 1 else 0
                if exhausted:
                    m.chunks_failed += 1
                else:
                    m.chunks_successful += 1
                outside = bool(self._core_ids) and chunk.chunk_id not in self._core_ids
                for raw in raw_items:
                    criterion = self._to_criterion(raw, chunk, f"C{len(criteria) + 1:03d}")
                    if criterion and outside and criterion.operator == "WITHIN_LAST_N_FINANCIAL_YEARS":
                        continue                  # 'financial statements for the last 5 years' in a submission list
                    if criterion and outside and criterion.field == "other" and criterion.operator != "SUBMITTED":
                        # a page outside the eligibility section is read only for checkable facts (blacklisting,
                        # certificates, turnover...) and declarations; a loose 'other' item there is boilerplate
                        log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                                          status="DROPPED", message=f"loose item outside the eligibility section: {criterion.source_text[:90]}")
                        continue
                    if criterion:
                        criterion.group = self._groups.group_for(chunk, criterion.source_text)
                        criteria.append(criterion)

        await _process(work)

        if not criteria and m.chunks_successful and self.plan_info.get("mode") == "eligibility section located":
            # The located section produced nothing although the model answered: the heading may have been a false
            # match. Never end with an empty checklist; read the pages that look most like eligibility text instead.
            read = {c.chunk_id for c, _ in work}
            rest = [c for c in candidates if c.chunk_id not in read]
            keep, scores = select_chunks(rest, settings.ELIGIBILITY_PREFILTER_MAX_FRACTION) if rest else (set(), {})
            best = sorted((c for c in rest if c.chunk_id in keep), key=lambda c: (-scores.get(c.chunk_id, 0), c.physical_page))
            second = [(c, "prose") for c in sorted(best[:FALLBACK_MAX_PAGES], key=lambda c: c.physical_page)]
            if second:
                log_pipeline_step("S6_LLM_EXTRACTOR", status="FALLBACK",
                                  message=f"no criteria in the located section; reading {len(second)} more page(s)")
                m.candidate_chunks += len(second)
                self.plan_info["fallback_pages_read"] = sorted({c.physical_page for c, _ in second})
                await _process(second)

        log_pipeline_step("S6_LLM_EXTRACTOR", status="COMPLETED",
                          message=f"{len(criteria)} criteria; attempts={m.total_attempts} failed={m.failed_calls}")
        metrics = m.as_dict()
        metrics["plan"] = self.plan_info
        metrics["model"] = self.options.resolved_model()
        metrics["num_ctx"] = self.options.resolved_num_ctx()
        return criteria, metrics

    async def _extract_chunk(self, chunk: ChunkSchema, m: ExtractionMetrics) -> Tuple[List[dict], int, bool]:
        prompt_chunk = chunk
        if chunk.chunk_id in self._allowed_blocks:       # its table rows are handled row by row: do not send them twice
            prompt_chunk = chunk.model_copy(update={"chunk_text": f"--- [PAGE {chunk.physical_page}] ---\n"
                                                    + self._outside_tables(chunk.chunk_text)})
        user_prompt = build_extraction_user_prompt(prompt_chunk)
        attempts = max(1, settings.ELIGIBILITY_MAX_ATTEMPTS)
        last_err: Optional[Exception] = None

        for attempt in range(attempts):
            m.total_attempts += 1
            if attempt:
                m.retry_count += 1
            try:
                content = await llm_call.chat_json(
                    extraction_system_prompt(self.options.instructions), user_prompt, EXTRACTION_JSON_SCHEMA,
                    attempt=attempt, options=self.options,
                )
                parsed = parse_json_robust(content, required_key="source_text")
                m.successful_calls += 1
                items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
                return [p for p in items if isinstance(p, dict)], attempt + 1, False
            except Exception as e:
                m.failed_calls += 1
                last_err = e
                log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                                  status="ATTEMPT_FAILED", message=f"attempt {attempt + 1}/{attempts}: {type(e).__name__}: {e}")
                if attempt < attempts - 1:
                    await asyncio.sleep(_BACKOFF_S[min(attempt, len(_BACKOFF_S) - 1)])

        log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                          status="RETRY_EXHAUSTED", message=f"{type(last_err).__name__}: {last_err}")
        return [], attempts, True

    @staticmethod
    def _to_criterion(raw: dict, chunk: ChunkSchema, criterion_id: str) -> Optional[CriterionSchema]:
        src = str(raw.get("source_text") or "").strip()
        if src.upper() in _NULLISH:
            log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                              status="DROPPED", message=f"model item without a quote dropped: {str(raw)[:120]}")
            return None
        value = raw.get("value", "")
        field_id = canonicalize_field(str(raw.get("field") or "other").strip())
        if _SCORING_QUOTE.search(src):
            log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                              status="DROPPED", message=f"evaluation scoring, not eligibility: {src[:90]}")
            return None
        if field_id in _NUMERIC_FIELDS and raw.get("operator") in _COMPARISONS and not re.search(r"\d", str(value)) \
                and Normalizer.parse_numeric(value) is None:
            return None                           # a threshold with no number in it ('!= exemption') is not a threshold
        if field_id in _NUMERIC_FIELDS - {"bid_validity_days"} and raw.get("operator") in (">=", "==", "<=") \
                and Normalizer.parse_numeric(value) == 0:
            return None                           # 'at least 0' states no requirement
        if _FORM_ENTRY.match(src) and raw.get("operator") != "SUBMITTED":
            raw = {**raw, "operator": "SUBMITTED"}  # 'Form 4: Power of Attorney' is a document to hand in
        if field_id.startswith(("role_", "team_")) and is_latin(src) and not _PEOPLE_WORDS.search(src):
            log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                              status="DROPPED", message=f"role field '{field_id}' on text that names no people: {src[:100]}")
            return None
        if field_id == "experience_years" and is_latin(src) and not _EXPERIENCE_WORDS.search(src):
            return None
        if field_id == "other" and str(value).strip().lower() in ("true", "yes") and _DECLARATION.match(src):
            raw = {**raw, "operator": "SUBMITTED"}        # 'I/We hereby confirm ...' is a declaration to sign, not a fact to check
        if value in (None, "", [], "[]", "N/A") and str(raw.get("operator") or "").upper() != "SUBMITTED":
            log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                              status="DROPPED", message=f"model item with an empty value dropped: {str(raw)[:120]}")
            return None
        try:
            return CriterionSchema(
                criterion_id=criterion_id,
                chunk_id=chunk.chunk_id,
                page_no=chunk.physical_page,
                section=raw.get("section") or chunk.section or chunk.chapter or f"Page {chunk.physical_page}",
                field=canonicalize_field(str(raw.get("field") or "other").strip()),
                operator=canonical_operator(raw.get("operator"), value),
                value=value,
                unit=raw.get("unit"),
                mandatory=(str(raw.get("mandatory", True)).strip().lower() not in ("false", "no", "0", "optional")),
                source_text=src,
            )
        except Exception as ex:
            log_pipeline_step("S6_LLM_EXTRACTOR", chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                              status="PARSE_ERROR", message=f"invalid criterion: {ex}")
            return None
