"""Deterministic (non-AI) reasoning text and merge of LLM explanations into results."""
from typing import Dict, List

from app.schemas.eligibility import CriterionResultSchema


def fallback_reasoning(r: CriterionResultSchema) -> str:
    text = _headline(r)
    detail = " ".join(str(r.evidence or "").split())
    if r.status in ("NEEDS_REVIEW", "REVIEW", "MISSING", "FAIL") and detail and detail.lower() not in text.lower() \
            and "no automatic" not in detail.lower():
        text += " " + detail
    return text


def _headline(r: CriterionResultSchema) -> str:
    from app.services.eligibility.verdict import field_label
    name = field_label(r.field) if r.field else "Specification"
    company = str(r.company_value).strip() if r.company_value is not None else "nothing recorded"
    from app.services.eligibility.verdict import requirement_text, shorten
    required = requirement_text(r.operator, r.tender_value, r.source_text)
    if r.field == "other" and r.source_text:
        required = shorten(r.source_text, 140)             # '>= 150' alone says nothing: use the tender's own words

    if r.status == "PASS":
        return f"Met. The company record ('{company}') satisfies the requirement: {name}."
    if r.status == "FAIL":
        return f"Not met. The company record ('{company}') does not reach what the tender asks for ({required})."
    if r.status == "MISSING":
        return (f"We cannot check this: the company records have nothing about {name.lower()}. "
                "Add it to the Knowledge Base before bidding.")
    if r.status in ("NEEDS_REVIEW", "REVIEW"):
        return f"A person must check this against the company records. The tender says: \"{required}\""
    if r.status == "INFORMATIONAL":
        return "For information only. This is a procedure or date in the tender, not something the company must prove."
    return f"Status {r.status}: please check this requirement against the company records."


def apply_reasoning(results: List[CriterionResultSchema], llm_reasons: Dict[str, str]) -> List[CriterionResultSchema]:
    """Set ai_reasoning from the LLM where available, otherwise the deterministic fallback."""
    for r in results:
        text = (llm_reasons.get(r.criterion_id) or "").strip()
        r.ai_reasoning = text or fallback_reasoning(r)
    return results
