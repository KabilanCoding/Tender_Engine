"""S10 - LLM-written audit explanations for evaluated criteria.

Returns {criterion_id: text}. Deterministic fallback wording lives in
app.services.eligibility.reasoning (no AI), so a failed LLM call never blocks a report.
"""
import asyncio
import re
from typing import Any, Dict, List, Optional

from app.ai.tender import llm_call
from app.ai.tender.json_parse import parse_json_robust
from app.ai.tender.run_options import RunOptions
from app.ai.tender.prompts import (
    REASONING_JSON_SCHEMA,
    REASONING_SYSTEM_PROMPT,
    build_reasoning_user_prompt,
)
from app.core.config import settings
from app.schemas.eligibility import CriterionResultSchema
from app.services.eligibility.pipeline_log import log_pipeline_step

_ID_KEYS = ("criterion_id", "criterionId", "id")
_TEXT_KEYS = ("ai_reasoning", "reasoning", "explanation", "audit_reasoning")


def _first(d: dict, keys) -> Any:
    return next((d[k] for k in keys if d.get(k)), None)


class ReasoningGenerator:
    @classmethod
    async def explain(
        cls, results: List[CriterionResultSchema], overall_verdict: str, options: Optional[RunOptions] = None
    ) -> Dict[str, str]:
        if not results:
            return {}
        size = max(1, settings.ELIGIBILITY_REASONING_BATCH)
        batches = [results[i:i + size] for i in range(0, len(results), size)]
        parts = await asyncio.gather(*[cls._explain_batch(b, overall_verdict, options) for b in batches],
                                     return_exceptions=True)
        merged: Dict[str, str] = {}
        for part in parts:
            if isinstance(part, dict):
                merged.update(part)
        log_pipeline_step("S10_LLM_REASONING", status="COMPLETED",
                          message=f"LLM reasoning for {len(merged)}/{len(results)} criteria")
        return merged

    @classmethod
    async def _explain_batch(cls, batch: List[CriterionResultSchema], overall_verdict: str,
                             options: Optional[RunOptions] = None) -> Dict[str, str]:
        items = [{
            "criterion_id": r.criterion_id,
            "field": r.field,
            "tender_requirement": r.tender_value,
            "company_value": None if r.company_value is None else str(r.company_value),
            "status": r.status,
            "page_no": r.page_no,
            "source_text": (r.source_text or "")[:300],
            "evidence": r.evidence,
        } for r in batch]
        prompt = build_reasoning_user_prompt(items, overall_verdict)

        for attempt in range(2):  # primary, then fallback model / plain JSON mode
            try:
                content = await llm_call.chat_json(
                    REASONING_SYSTEM_PROMPT, prompt, REASONING_JSON_SCHEMA,
                    attempt=attempt, temperature=0.1, options=options,
                )
                return cls._map_reasons(parse_json_robust(content, required_key="ai_reasoning"), batch)
            except Exception as e:
                log_pipeline_step("S10_LLM_REASONING", status="WARNING",
                                  message=f"reasoning attempt {attempt + 1} failed: {type(e).__name__}: {e}")
        return {}

    @staticmethod
    def _numbers(text: Any) -> set:
        return {re.sub(r"\D", "", n) for n in re.findall(r"\d[\d,.]*", str(text or "")) if re.sub(r"\D", "", n)}

    _CODES = re.compile(r"\b(?:PASS|FAIL|MISSING|NEEDS_REVIEW|INFORMATIONAL)\b|[{}\[\]]|\"|\bnull\b|\bnone\b|criterion_id|ai_reasoning", re.I)
    _SAYS_NOT_MET = re.compile(r"\b(?:does not meet|do not meet|doesn't meet|fails?|not met|not satisfied|is not eligible)\b", re.I)
    _SAYS_MET = re.compile(r"\b(?:meets|satisfies|fulfils|fulfills|is met|are met|is eligible)\b", re.I)

    _SAYS_SHORT = re.compile(r"\b(?:does not have|do not have|not enough|insufficient|lacks?|below|fewer|less than)\b", re.I)
    _FILLER = re.compile(r"\bthe other criterion\b|\bthe system(?:'s)?\b|\bthe evidence (?:provided|shows|does)\b|"
                         r"\bthe tender does not\b|\bdoes not (?:provide|demonstrate|specify)\b", re.I)

    @classmethod
    def _faithful(cls, text: str, r: CriterionResultSchema) -> bool:
        """An explanation may only quote numbers the item contains, must not claim the opposite of its status, and must
        read like a short human sentence (a small model sometimes leaks JSON, status codes or repeats itself)."""
        allowed = cls._numbers(" ".join(str(x or "") for x in (
            r.tender_value, r.company_value, r.source_text, r.evidence, r.criterion_id)))
        if not cls._numbers(text) <= allowed:
            return False
        if not 15 <= len(text) <= 320 or len(text.split()) > 60:
            return False
        if re.search(r"(?i)\b(?:status|page number|page no)\b", text):
            return False
        if cls._CODES.search(text) or cls._FILLER.search(text):
            return False
        sentences = [s.strip().lower() for s in re.split(r"[.!?]+", text) if s.strip()]
        if len(sentences) != len(set(sentences)):
            return False                                           # says the same thing twice
        if r.status == "PASS" and cls._SAYS_NOT_MET.search(text):
            return False
        if r.status != "PASS" and cls._SAYS_MET.search(text) and not re.search(r"\bnot\b|\bno\b|cannot|can't|unless", text, re.I):
            return False
        if r.status in ("MISSING", "NEEDS_REVIEW") and (cls._SAYS_NOT_MET.search(text) or cls._SAYS_SHORT.search(text)):
            return False                                           # unknown is not 'failed'
        if r.status == "MISSING" and not re.search(
                r"\b(?:no|not recorded|not found|not available|cannot|can't|missing|nothing|add|record)\b", text, re.I):
            return False                                           # a MISSING item must say the data is absent
        return True

    @classmethod
    def _map_reasons(cls, data: Any, batch: List[CriterionResultSchema]) -> Dict[str, str]:
        if not isinstance(data, list):
            return {}
        by_id = {r.criterion_id: r for r in batch}
        wanted = set(by_id)
        out: Dict[str, str] = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue
            cid, text = _first(entry, _ID_KEYS), _first(entry, _TEXT_KEYS)
            if cid and text and str(cid).strip() in wanted:  # ignore ids the model made up
                text = " ".join(str(text).split())
                if cls._faithful(text, by_id[str(cid).strip()]):       # otherwise the deterministic wording is used
                    out[str(cid).strip()] = text
                else:
                    log_pipeline_step("S10_LLM_REASONING", criterion_id=str(cid), status="REJECTED",
                                      message="explanation contradicted or invented facts; using the rule-based wording")
        return out
