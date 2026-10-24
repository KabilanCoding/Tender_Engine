"""Orchestrates the tender eligibility pipeline: S1-S4 (parse), S6 (LLM), S7 (validate), evaluate, verdict.

The LLM stages are injected (`extractor`, `explain`) so this module stays free of AI imports and the
whole flow can be tested without a model.
"""
import asyncio
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Tuple

from app.core.config import settings
from app.schemas.eligibility import ChunkSchema, CriterionResultSchema, CriterionSchema
from app.services.eligibility.chunker import Chunker
from app.core.heavy import run_stage
from app.services.eligibility.bid_conditions import find_bid_conditions
from app.services.eligibility.deadlines import deadline_warning, find_key_dates
from app.services.eligibility.company_alignment import CompanyAligner
from app.services.eligibility.company_facts import CompanyFacts
from app.services.eligibility.errors import FileValidationError, PipelineError
from app.services.eligibility.file_validator import FileValidator
from app.services.eligibility.ocr_service import OCRService, OCRSession
from app.services.eligibility.pdf_extractor import PDFExtractor
from app.services.eligibility.post_validator import PostValidator
from app.services.eligibility.reasoning import apply_reasoning
from app.services.eligibility.rule_engine import RuleEngine
from app.services.eligibility.structure_analyzer import StructureAnalyzer
from app.services.eligibility.verdict import VerdictAggregator
from app.services.eligibility import trace

Progress = Callable[..., None]  # (message, level, stage=None, metrics=None)
TEXT_PAGE_CHARS = 3000


class Extractor(Protocol):
    async def extract(self, chunks: List[ChunkSchema], on_progress=None) -> Tuple[List[CriterionSchema], Dict[str, Any]]: ...


Explain = Callable[[List[CriterionResultSchema], str], Awaitable[Dict[str, str]]]


def text_to_pages(text: str, page_chars: int = TEXT_PAGE_CHARS) -> List[Dict[str, Any]]:
    """Pseudo-pages for non-PDF input (DOCX/TXT already converted to text by the parsers)."""
    lines = [p.strip() for p in (text or "").split("\n") if p.strip()]
    paragraphs: List[Tuple[str, str]] = []           # (text, "text" | "table"); consecutive "| a | b |" lines = one table
    for ln in lines:
        is_row = ln.startswith("|") or ln.count("|") >= 2
        if is_row and paragraphs and paragraphs[-1][1] == "table":
            paragraphs[-1] = (paragraphs[-1][0] + "\n" + ln, "table")
        else:
            paragraphs.append((ln, "table" if is_row else "text"))
    pages: List[Dict[str, Any]] = []
    blocks: List[Dict[str, Any]] = []
    size = 0
    for para, kind in paragraphs:
        if size + len(para) > page_chars and blocks:
            pages.append({"page_no": len(pages) + 1, "blocks": blocks, "char_count": size, "is_scanned": False})
            blocks, size = [], 0
        blocks.append({"text": para, "bbox": (0, size, 1, size + 1), "is_heading": False, "type": kind})
        size += len(para)
    if blocks:
        pages.append({"page_no": len(pages) + 1, "blocks": blocks, "char_count": size, "is_scanned": False})
    return pages


# above these sizes a step runs in its own process (see app/core/heavy.py); smaller documents stay in a thread
_BIG_FILE_BYTES = 2_000_000
_BIG_DOC_PAGES = 60
_BIG_DOC_CHARS = 250_000
_BIG_CHUNKS = 150


class EligibilityPipeline:
    def __init__(self, extractor: Extractor, explain: Optional[Explain] = None, progress: Optional[Progress] = None,
                 amend: Optional[Callable[[str], Awaitable[List[Dict[str, str]]]]] = None,
                 semantic: Optional[Callable[[List[CriterionSchema]], Awaitable[Dict[str, Dict[str, Any]]]]] = None,
                 checklist: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None):
        self.semantic = semantic
        self.checklist = checklist
        self.extractor = extractor
        self.amend = amend
        self.explain = explain
        self._progress = progress or (lambda message, level="info", **kw: None)
        self.stages: List[Dict[str, Any]] = []   # per-stage artifacts shown in the JSON inspector

    def _say(self, message: str, level: str = "info", stage: Optional[str] = None,
             metrics: Optional[Dict[str, Any]] = None) -> None:
        kwargs: Dict[str, Any] = {}
        if stage:
            kwargs["stage"] = stage
        if metrics:
            kwargs["metrics"] = metrics
        self._progress(message, level, **kwargs)

    def _record(self, stage_id: str, step: str, output: Dict[str, Any], status: str = "COMPLETED") -> None:
        self.stages.append({"stage_id": stage_id, "step": step, "status": status, "output": output})

    # ------------------------------------------------------------ parse (S1-S4)
    async def parse(self, run_id: str, filename: str, file_bytes: Optional[bytes], text: Optional[str]) -> List[ChunkSchema]:
        is_pdf = bool(file_bytes) and filename.lower().endswith(".pdf")
        if is_pdf:
            self._say("Validating document…", "working", stage="S1")
            big_file = len(file_bytes or b"") > _BIG_FILE_BYTES
            info = await run_stage(FileValidator.validate_file, filename, file_bytes, run_id, heavy=big_file, name="file check")
            self._record("S1", "S1 File Validation", info)
            trace.file_check(info)
            self._say("Extracting text and layout from PDF…", "working", stage="S2A")
            data = await run_stage(PDFExtractor.extract_pdf_data, file_bytes, heavy=big_file, name="text extraction")
            pages = data["pages"]
            ocr_pages = [p["page_no"] for p in pages if p["is_scanned"]]
            self._record("S2A", "S2a Document Text Extraction", {
                "total_pages": data["total_pages"], "scanned_pages": ocr_pages,
                "chars_per_page": [p["char_count"] for p in pages][:200]})
            if ocr_pages:
                self._say(f"Running OCR on {len(ocr_pages)} scanned page(s)…", "working", stage="S2B")
                ocr_session = OCRSession()
                languages_by_page: Dict[int, str] = {}
                confidence_by_page: Dict[int, float] = {}
                notes: List[str] = []
                for p in pages:
                    if p["is_scanned"] and p.get("has_images", True):
                        ocr = await asyncio.to_thread(OCRService.process_scanned_page, file_bytes, p["page_no"], ocr_session)
                        p["blocks"], p["char_count"] = ocr["blocks"], ocr["char_count"]
                        p["ocr_used"] = ocr["ocr_used"]
                        languages_by_page[p["page_no"]] = ocr.get("languages", "eng")
                        confidence_by_page[p["page_no"]] = ocr.get("confidence", 0.0)
                        notes += [f"Page {p['page_no']}: {n}" if "confidence" in n else n
                                  for n in ocr.get("notes", []) if n not in notes]
                for n in notes:
                    self._say(n, "warning")
                empty = [p["page_no"] for p in pages if p["is_scanned"] and not p.get("char_count")]
                if empty:
                    self._say(f"No text could be read from page(s) {empty[:10]}; is Tesseract installed? "
                              "Requirements on those pages will be missed.", "warning")
                self._record("S2B", "S2b Scanned Page Reader", {
                    "pages": ocr_pages, "ocr_used": [p["page_no"] for p in pages if p.get("ocr_used")],
                    "unreadable_pages": empty, "languages_by_page": languages_by_page, "confidence_by_page": confidence_by_page,
                    "language_warnings": notes, "installed_languages": OCRService.installed_languages()})
                trace.pages_text(pages, "03_ocr_pages", "OCR TEXT", only_ocr=True)
            total_pages = data["total_pages"]
        else:
            if not (text or "").strip():
                raise PipelineError("Document has no extractable text.", run_id=run_id)
            self._say("Validating document…", "working", stage="S1")
            info = await asyncio.to_thread(FileValidator.validate_text, filename, text or "", run_id)
            self._record("S1", "S1 File Validation", info)
            trace.file_check(info)
            pages = text_to_pages(text or "")
            total_pages = len(pages)
        trace.pages_text(pages, "02_text_per_page", "TEXT READ FROM THE DOCUMENT")

        self._say("Detecting document structure…", "working", stage="S3")
        big = total_pages > _BIG_DOC_PAGES or sum(p.get("char_count", 0) for p in pages) > _BIG_DOC_CHARS
        nodes = await run_stage(StructureAnalyzer.analyze_structure, pages, heavy=big, name="structure detection")
        kinds: Dict[str, int] = {}
        for n in nodes:
            kinds[n["type"]] = kinds.get(n["type"], 0) + 1
        self._record("S3", "S3 Structure Analyzer", {"nodes": len(nodes), "by_type": kinds})
        trace.structure(nodes)
        flags = {p["page_no"]: (p.get("is_scanned", False), p.get("ocr_used", False)) for p in pages}
        for n in nodes:
            n["is_scanned"], n["ocr_used"] = flags.get(n.get("page_no"), (False, False))
        self._say("Splitting into clauses and page chunks…", "working", stage="S4")
        chunks = await run_stage(Chunker.create_chunks, run_id, nodes, total_pages, heavy=big, name="page splitting")
        self._record("S4", "S4 Clause Segmentation", {
            "chunks": len(chunks), "total_chars": sum(c.char_count for c in chunks),
            "sample": [{"chunk_id": c.chunk_id, "page": c.physical_page, "chars": c.char_count,
                        "preview": c.chunk_text[:160]} for c in chunks[:5]]})
        trace.chunks(chunks)
        self._say(f"Parsed {total_pages} page(s) into {len(chunks)} chunk(s)", "success",
                  metrics={"total_chunks": len(chunks)})
        return chunks

    @staticmethod
    def _is_corrigendum(chunks: List[ChunkSchema]) -> bool:
        """A short document that calls itself a corrigendum / addendum / amendment to a tender."""
        pages = {c.physical_page for c in chunks}
        head = " ".join(c.chunk_text for c in chunks if c.physical_page <= 2)[:3000].lower()
        return len(pages) <= 12 and bool(re.search(r"\b(?:corrigendum|addendum|amendment)\b", head)) \
            and bool(re.search(r"\bamend|\bexisting clause|\bamended clause|\bhereby\b|\bstand\s+amended", head))

    async def _full_checklist(self, chunks: List[ChunkSchema], criteria: List[CriterionSchema]) -> Optional[Dict[str, Any]]:
        """S11: read the whole tender for the full checklist. Never changes the verdict; a failure only leaves the checklist out."""
        from app.ai.tender.checklist import mark_compared

        async def on_progress(done: int, total: int, found: int) -> None:
            self._say(f"Full checklist: reading part {min(done + 1, total)} of {total}, {found} item(s) listed so far", "working",
                      stage="S11" if done == 0 else None)

        self._say("Reading the whole tender for the full checklist…", "working", stage="S11")
        try:
            out = await self.checklist(chunks, on_progress=on_progress)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._record("S11", "S11 Full Tender Checklist", {"error": f"{type(e).__name__}: {e}"}, status="FAILED")
            self._say("The full checklist could not be produced; the eligibility result above is not affected.", "warning")
            return None
        dropped = out.pop("dropped", [])
        compared = mark_compared(out["items"], criteria)
        trace.checklist(out, dropped)
        out["compared"] = compared
        m = out["metrics"]
        self._record("S11", "S11 Full Tender Checklist", {"metrics": m, "items": len(out["items"]), "compared_with_company": compared})
        if m.get("failed_windows"):
            self._say(f"{m['failed_windows']} part(s) of the tender could not be read by the AI; the checklist may be incomplete.", "warning")
            out["incomplete"] = True
        self._say(f"Full checklist: {len(out['items'])} item(s) listed from the whole tender.", "success")
        return out

    # ------------------------------------------------------------ full run
    async def run(self, run_id: str, filename: str, file_bytes: Optional[bytes], text: Optional[str],
                  facts: CompanyFacts) -> Dict[str, Any]:
        t0 = time.time()
        chunks = await self.parse(run_id, filename, file_bytes, text)

        async def on_progress(done: int, total: int, calls: int, found: int) -> None:
            self._say(f"AI extraction: {done}/{total} chunks processed, {found} criteria found so far", "working",
                      stage="S6" if done == 0 else None,
                      metrics={"chunks_started": done, "llm_candidate_chunks": total,
                               "actual_llm_api_calls": calls, "raw_criteria_found": found})

        self._say(f"Locating the eligibility section in {len(chunks)} page chunk(s)…", "working", stage="S5")
        raw, llm_metrics = await self.extractor.extract(chunks, on_progress=on_progress)
        if llm_metrics.get("llm_candidate_chunks") and llm_metrics.get("chunks_failed") == llm_metrics["llm_candidate_chunks"]:
            raise PipelineError("The AI model failed on every chunk; check that the LLM provider is running.", run_id=run_id)
        trace.raw_criteria(raw)
        self._say(f"AI extracted {len(raw)} raw criteria", "success")
        if llm_metrics.get("plan"):
            self._record("S5", "S5 Eligibility Locator", llm_metrics["plan"])
        self._record("S6", "S6 Criteria Analysis", {
            "metrics": llm_metrics,
            "raw_criteria": [{"id": c.criterion_id, "field": c.field, "operator": c.operator,
                              "value": c.value, "page": c.page_no} for c in raw]})

        self._say("Verifying quotes against the tender text and removing duplicates…", "working", stage="S7")
        large = len(chunks) > _BIG_CHUNKS
        criteria, val_metrics = await run_stage(PostValidator.validate_and_deduplicate, raw, chunks, run_id,
                                                heavy=large, name="quote check")
        trace.validated(raw, criteria, val_metrics)
        unverified = sum(1 for c in criteria if not c.exact_match)
        self._say(f"{len(criteria)} criteria kept ({unverified} with unverified quotes)", "success")
        self._record("S7", "S7 Citation & Evidence Check", {
            "metrics": val_metrics,
            "criteria": [{"id": c.criterion_id, "field": c.field, "grounded": c.exact_match,
                          "source_text": c.source_text[:200]} for c in criteria]})

        extra = find_bid_conditions(chunks, criteria)
        if extra:
            criteria = criteria + extra
            self._say(f"{len(extra)} bid condition(s) found in the text (fees, consortium, source code ...).", "info")
        self._say("Aligning each requirement with the company knowledge base…", "working", stage="S8")
        criteria, align_metrics = await run_stage(CompanyAligner.align, criteria, facts, heavy=large, name="company matching")
        self._record("S8", "S8 Company Data Alignment", align_metrics)
        if align_metrics["no_company_data"]:
            self._say(f"{len(align_metrics['no_company_data'])} requirement(s) ask for facts the knowledge base does not hold yet.",
                      "info")

        if facts.has_any_data:
            s = facts.summary()
            self._say(f"Comparing with company knowledge base ({s['certifications']} certifications, "
                      f"{s['projects']} projects, {s['financial_years']} financial years, {s['employees']} employees)…",
                      "working", stage="S9")
        else:
            self._say("Knowledge base is empty: criteria will be reported as MISSING, not guessed.", "info", stage="S9")
        if self.semantic and (facts.projects or facts.employees):
            try:
                matched = await self.semantic(criteria)
            except Exception:
                matched = {}
            for c in criteria:
                m = matched.get(c.criterion_id)
                if not m:
                    continue
                extra = {}
                if m.get("projects"):
                    extra["semantic_projects"] = m["projects"]["names"]
                    extra["semantic_reasons"] = m["projects"].get("reasons", {})
                if m.get("employees"):
                    extra["semantic_employees"] = m["employees"]["names"]
                    extra["semantic_reasons"] = {**extra.get("semantic_reasons", {}), **m["employees"].get("reasons", {})}
                c.alignment = {**(c.alignment or {}), **extra}
            if matched:
                self._say(f"Matched past projects / people to {len(matched)} requirement(s) by meaning (shown as 'check by hand').", "info")
        results = await run_stage(RuleEngine.evaluate, criteria, facts, heavy=large, name="company comparison")
        self._record("S9", "S9 Company Master Audit", {
            "knowledge_base": facts.summary(),
            "results": [{"id": r.criterion_id, "field": r.field, "status": r.status, "evidence": r.evidence}
                        for r in results]})
        trace.comparison(results)
        self._say("Computing verdict…", "working", stage="S10")
        verdict = VerdictAggregator.aggregate(results)
        verdict["key_dates"] = find_key_dates(chunks)
        verdict["deadline_warning"] = deadline_warning(verdict["key_dates"])
        if verdict["deadline_warning"]:
            self._say(verdict["deadline_warning"], "warning")
        if self._is_corrigendum(chunks):
            verdict["document_type"] = "corrigendum"
            verdict["summary"] = ("This document is a corrigendum (an amendment to a tender), not a full tender: the items below come "
                                  "from the amended clauses only. Analyse the original tender with these amendments applied. "
                                  + verdict["summary"])
            self._say("This looks like a corrigendum: only the amended clauses were analysed.", "warning")
            if self.amend:
                try:
                    changes = await self.amend("\n".join(c.chunk_text for c in chunks))
                except Exception:
                    changes = []
                verdict["amendments"] = changes
                if changes:
                    from app.ai.tender.amendments import describe
                    verdict["summary"] += describe(changes)
                    self._say(f"{len(changes)} change(s) listed from the corrigendum.", "info")
                else:
                    verdict["summary"] += (" The changes this corrigendum makes could not be listed automatically; "
                                           "read its 'Amended clause' column (dates, eligibility wording, technology list).")
                    self._say("The corrigendum's changes could not be listed automatically.", "warning")

        failed_chunks = int(llm_metrics.get("chunks_failed") or 0)
        if failed_chunks:
            # some pages were never read by the model: requirements may be missing, so never claim ELIGIBLE
            self._say(f"AI could not read {failed_chunks} page chunk(s); the result may be incomplete.", "warning")
            verdict["incomplete_extraction"] = True
            if verdict["status"] == "ELIGIBLE":
                verdict["status"] = "PARTIAL"
            verdict["summary"] += f" Warning: {failed_chunks} page chunk(s) could not be analysed by the AI model."

        llm_reasons: Dict[str, str] = {}
        if self.explain and results:
            self._say("Writing audit explanations…", "working")
            # Every evaluated item gets a written reasoning, most important first (the item cap keeps a run bounded;
            # the rest, and any item the model gets wrong or skips, keep the deterministic wording).
            order = {"FAIL": 0, "NEEDS_REVIEW": 1, "MISSING": 2, "PASS": 3}
            targets = sorted((r for r in results if r.status in order), key=lambda r: (order[r.status], r.criterion_id))
            targets = targets[:settings.ELIGIBILITY_REASONING_MAX_ITEMS]
            try:
                llm_reasons = await self.explain(targets, verdict["status"]) if targets else {}
            except Exception:
                llm_reasons = {}
        apply_reasoning(results, llm_reasons)
        self._record("S10", "S10 Verdict Computation", {
            "verdict": verdict, "llm_explanations": len(llm_reasons)})

        checklist = await self._full_checklist(chunks, criteria) if self.checklist else None
        trace.finish(filename)
        return {
            "stages": self.stages,
            "results": results,
            "verdict": verdict,
            "checklist": checklist,
            "metrics": {
                "llm": llm_metrics,
                "validation": val_metrics,
                "chunks": len(chunks),
                "kb": facts.summary(),
                "duration_s": round(time.time() - t0, 1),
            },
        }
