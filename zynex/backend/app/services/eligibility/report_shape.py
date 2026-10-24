"""Serialises evaluated criteria into the JSON stored on EligibilityReport.criteria.

Keeps the legacy keys (criterion/required/company_status/evidence) so existing screens still render,
and adds the fields the new compliance matrix needs.
"""
from typing import Any, Dict, List

from app.schemas.eligibility import CriterionResultSchema

_LEGACY_STATUS = {"PASS": "met", "FAIL": "not_met"}


def _title(r: CriterionResultSchema) -> str:
    from app.services.eligibility.verdict import plain_title
    return plain_title(r.field, r.source_text, r.tender_value)


def _required(r: CriterionResultSchema) -> str:
    from app.services.eligibility.verdict import requirement_text
    return requirement_text(r.operator, r.tender_value, r.source_text)


def to_report_rows(results: List[CriterionResultSchema]) -> List[Dict[str, Any]]:
    return [{
        # legacy shape
        "criterion": _title(r),
        "required": _required(r),
        "tender_value": r.tender_value,
        "company_status": _LEGACY_STATUS.get(r.status, "unknown"),
        "evidence": r.evidence or "",
        # compliance matrix fields
        "criterion_id": r.criterion_id,
        "field": r.field,
        "operator": r.operator,
        "status": r.status,
        "mandatory": r.mandatory,
        "page_no": r.page_no,
        "section": r.section,
        "source_text": r.source_text,
        "grounded": r.grounded,
        "is_document": r.is_document,
        "alt_group": r.alt_group,
        "group": r.group,
        "company_value": None if r.company_value is None else str(r.company_value),
        "reasoning": r.ai_reasoning,
    } for r in results]
