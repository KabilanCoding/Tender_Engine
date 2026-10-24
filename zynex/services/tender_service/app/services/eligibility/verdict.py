"""Overall eligibility verdict, missing-document list and compliance counts from evaluated criteria."""
import re
from collections import Counter
from typing import Any, Dict, List

from app.schemas.eligibility import CriterionResultSchema

_BLOCKING_UNKNOWN = ("MISSING", "NEEDS_REVIEW")


_ACRONYMS = {"dsc", "gst", "pan", "emd", "iso", "cmmi", "msme", "epf", "esi", "sla", "boq", "dr", "rpo", "rto", "csp", "os",
             "db", "ca", "pat", "psu", "govt", "udyam", "ha", "it", "cv", "cvs", "id", "pq", "tds", "fy", "erp", "ats", "ip", "vapt"}
_ACRONYM_TEXT = {"govt": "Govt."}


# Plain names for the fields people see most; anything else is the field id written out in words.
_PLAIN_NAMES = {
    "experience_years": "Years of experience", "years_in_business": "Years in business",
    "contract_count": "Number of completed projects", "similar_work_value": "Value of a similar past project",
    "project_value": "Value of a past project", "annual_turnover": "Yearly turnover", "net_worth": "Net worth",
    "incorporation_type": "Type of company", "state_office": "Office location", "blacklisted": "Not blacklisted",
    "insolvency_status": "Not bankrupt or insolvent", "company_website": "Company website",
    "employee_count": "Number of employees", "team_role_count": "Number of team members",
    "certifications": "Certificates", "emd_amount": "Bid security (EMD)", "bid_validity_days": "Bid validity",
    "non_blacklisting_declaration": "Declaration: not blacklisted", "working_capital": "Working capital",
    "gst_registration": "GST registration", "pan_card": "PAN card", "technologies": "Technologies and skills",
}

# What each status means, in words a first-time reader understands.
STATUS_TEXT = {
    "PASS": "Met", "FAIL": "Not met", "MISSING": "No company data", "NEEDS_REVIEW": "Check by hand",
    "INFORMATIONAL": "For information", "PROVISIONAL": "Not final",
}
_OP_TEXT = {">=": "At least", ">": "More than", "<=": "At most", "<": "Less than", "==": "Must be", "!=": "Must not be",
            "ALL_OF": "All of", "ANY_OF": "Any one of", "contains": "Must include", "AND": "All of", "OR": "Any one of",
            "SUBMITTED": "Hand in"}


def status_text(status: str) -> str:
    return STATUS_TEXT.get(status, str(status or "").replace("_", " ").capitalize())


def _tier_text(source_text: str) -> str:
    """'One work of 268.8 Cr, or two of 168 Cr, or three of 134.4 Cr' read back as alternatives, not a list of numbers."""
    from app.services.eligibility.rule_engine import _tiers      # imported here: rule_engine does not import this module
    tiers = _tiers(source_text or "")
    if not tiers:
        return ""
    names = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}

    def money(v: float) -> str:
        return f"{v / 1e7:g} Crore" if v >= 1e7 else f"{v / 1e5:g} Lakh"
    return "Either " + ", or ".join(f"{names.get(n, n)} work(s) of at least {money(v)} each" for n, v in tiers) + " (any one is enough)"


def requirement_text(operator, value, source_text: str = "") -> str:
    """'>= 10' -> 'At least 10'; 'ALL_OF [ISO 9001, CMMI Level 5]' -> 'All of: ISO 9001, CMMI Level 5'.
    A value that says nothing on its own (True/False) is replaced by the tender's own words."""
    op = str(operator or "").strip()
    tiers = _tier_text(source_text)
    if tiers:
        return tiers
    if (meaningless_value(value) or op == "SUBMITTED") and source_text:
        return shorten(source_text)
    items = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
    if len(items) == 1 and re.fullmatch(r"\d{6,}(?:\.\d+)?", items[0]):      # 15000000 -> 1.5 Crore
        n = float(items[0])
        items = [f"{n / 1e7:g} Crore" if n >= 1e7 else f"{n / 1e5:g} Lakh"]
    shown = ", ".join(items)
    if op in ("ALL_OF", "ANY_OF", "AND", "OR"):
        return f"{_OP_TEXT[op]}: {shown}" if len(items) > 1 else f"Must have: {shown}"
    if op == "contains":
        return f"Must include: {shown}"
    if op == "==" and len(items) == 1 and isinstance(value, str) and value.lower() in ("website", "true", "yes"):
        return "Must have a website"
    if op == "==" and len(items) == 1 and isinstance(value, str) and not value.replace(".", "").isdigit():
        return shorten(shown)
    return f"{_OP_TEXT.get(op, op)} {shown}".strip()


def field_label(field: str) -> str:
    """'dsc_required' -> 'DSC Required', 'contract_count' -> 'Number of completed projects'."""
    if field in _PLAIN_NAMES:
        return _PLAIN_NAMES[field]
    return " ".join(_ACRONYM_TEXT.get(w, w.upper()) if w in _ACRONYMS else w.capitalize()
                    for w in str(field or "").replace("_", " ").split())


def plain_title(field, source_text="", tender_value=None, limit: int = 80) -> str:
    """Short name of a requirement: its field in plain words, or (for 'other') the tender's own words."""
    if field and field != "other":
        return field_label(field)
    value = str(tender_value).strip() if tender_value is not None and not meaningless_value(tender_value) else ""
    if isinstance(tender_value, (list, tuple)):
        value = ", ".join(map(str, tender_value))
    return shorten(source_text or value or "Requirement", limit)


def _label(field: str) -> str:
    return field_label(field)


def shorten(text: str, limit: int = 140) -> str:
    """Cut at a word boundary with an ellipsis (never in the middle of a word)."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:-( ") + "\u2026"


def meaningless_value(value) -> bool:
    """A value that says nothing on its own (True/False/empty): show the tender's wording instead."""
    return value is None or isinstance(value, bool) or str(value).strip().lower() in ("true", "false", "none", "")


def _name(r: CriterionResultSchema) -> str:
    """Readable name of a criterion: its field, or (for 'other') the tender's own wording, never a Python list."""
    if r.field != "other":
        return _label(r.field)
    return plain_title("other", r.source_text, r.tender_value, limit=200) if r.source_text else shorten(
        ", ".join(map(str, r.tender_value)) if isinstance(r.tender_value, (list, tuple)) else str(r.tender_value))


_RANK = {"PASS": 0, "NEEDS_REVIEW": 1, "MISSING": 2, "FAIL": 3}


def collapse_alternatives(results: List[CriterionResultSchema]) -> List[CriterionResultSchema]:
    """Results of one 'X or Y or Z' requirement count once, as their best member (met beats unknown beats failed).
    The other members stay in the report; their evidence says they are alternatives."""
    groups: Dict[str, List[CriterionResultSchema]] = {}
    for r in results:
        if r.alt_group:
            groups.setdefault(r.alt_group, []).append(r)
    drop = set()
    for members in groups.values():
        best = min(members, key=lambda m: _RANK.get(m.status, 4))
        ids = ", ".join(m.criterion_id for m in members)
        for m in members:
            note = f" (One of the alternatives {ids}; meeting any one of them is enough.)"
            if note not in (m.evidence or ""):
                m.evidence = (m.evidence or "") + note
            if m is not best:
                drop.add(id(m))
    return [r for r in results if id(r) not in drop]


STATUS_WORDS = {"ELIGIBLE": "eligible", "PARTIAL": "cannot confirm yet", "PENDING": "nothing to check", "NOT_ELIGIBLE": "not eligible"}
_STATUS_RANK = {"ELIGIBLE": 0, "PARTIAL": 1, "PENDING": 2, "NOT_ELIGIBLE": 3}


def _category_key(label: str) -> str:
    return (label or "").split(" — ")[0]


class VerdictAggregator:
    @classmethod
    def aggregate(cls, results: List[CriterionResultSchema]) -> Dict[str, Any]:
        """One verdict for the tender. When the tender has several bidder categories (a bidder applies under ONE), each category is judged
        on its own requirements plus the ones that apply to everybody, and the headline is the best-fitting category."""
        keys = sorted({_category_key(r.group) for r in results if r.group})
        if len(keys) < 2:
            return cls._aggregate_one(results)
        common = [r for r in results if not r.group]
        groups = []
        for k in keys:
            mine = [r for r in results if _category_key(r.group) == k]
            label = next((r.group for r in mine if r.group), k)
            v = cls._aggregate_one(mine + common)
            groups.append({"key": k, "name": label, "status": v["status"], "summary": v["summary"], "counts": v["counts"]})
        best = min(groups, key=lambda g: (_STATUS_RANK.get(g["status"], 4), -g["counts"].get("pass", 0)))
        overall = cls._aggregate_one([r for r in results if not r.group or _category_key(r.group) == best["key"]])
        lines = "; ".join(f"{g['key']}: {STATUS_WORDS.get(g['status'], g['status'])}" for g in groups)
        overall["summary"] = (f"This tender has {len(groups)} bidder categories and a bidder applies under only one. Best fit: {best['key']}. "
                              f"{lines}. For {best['key']}: {overall['summary']}")
        overall["groups"] = groups
        overall["best_group"] = best["key"]
        return overall

    @classmethod
    def _aggregate_one(cls, results: List[CriterionResultSchema]) -> Dict[str, Any]:
        results = collapse_alternatives(results)
        counts = Counter(r.status for r in results)
        mandatory = [r for r in results if r.mandatory and r.status != "INFORMATIONAL"]
        # Forms, declarations and certificates to hand in are a to-do list (missing_documents / action checklist),
        # not something the knowledge base can prove or disprove, so they must not keep a bidder from ELIGIBLE.
        documents = [r for r in mandatory if r.is_document]
        mandatory = [r for r in mandatory if not r.is_document]
        failed = [r for r in mandatory if r.status == "FAIL"]
        unknown = [r for r in mandatory if r.status in _BLOCKING_UNKNOWN]
        passed = [r for r in mandatory if r.status == "PASS"]

        if not mandatory and documents:
            status = "PARTIAL"
            summary = (f"None of the requirements could be checked automatically; "
                       f"{len(documents)} document(s) must be prepared and attached.")
        elif not mandatory:
            status = "PENDING"
            summary = "No must-have requirements could be found in this document."
        elif failed:
            status = "NOT_ELIGIBLE"
            summary = (f"{len(failed)} must-have requirement{'' if len(failed) == 1 else 's'} not met, {len(passed)} met, "
                       f"{len(unknown)} could not be confirmed (out of {len(mandatory)}).")
        elif unknown:
            status = "PARTIAL"
            summary = (f"{len(passed)} of {len(mandatory)} must-have requirements met; "
                       f"{len(unknown)} could not be confirmed from the company records.")
        else:
            status = "ELIGIBLE"
            summary = f"All {len(mandatory)} must-have requirements are met."

        if documents and mandatory:
            summary += f" Plus {len(documents)} document(s) to prepare and attach."

        missing_documents: List[str] = []
        for r in results:
            if r.is_document and r.mandatory:
                label = _name(r)
                if label not in missing_documents:
                    missing_documents.append(label)

        return {
            "status": status,
            "summary": summary,
            "missing_documents": missing_documents,
            "counts": {
                "total": len(results),
                "mandatory": len(mandatory),
                "documents": len(documents),
                "pass": counts.get("PASS", 0),
                "fail": counts.get("FAIL", 0),
                "missing": counts.get("MISSING", 0),
                "needs_review": counts.get("NEEDS_REVIEW", 0),
                "informational": counts.get("INFORMATIONAL", 0),
            },
        }


def action_checklist(results: List[CriterionResultSchema], limit: int = 25) -> List[str]:
    """Plain-language to-do list for the bidder, derived only from mandatory criteria that are not met."""
    items: List[str] = []
    for r in collapse_alternatives(results):
        if not r.mandatory or r.status in ("PASS", "INFORMATIONAL"):
            continue
        name = _name(r)
        if r.is_document:
            items.append(f"Prepare and attach this document: {name}")
        elif r.status == "FAIL":
            items.append(f"Not met: {name}. {r.evidence or ''}".strip())
        elif r.status == "MISSING":
            items.append(f"Add to the company records: {name}. {r.evidence or ''}".strip())
        else:
            items.append(f"Check by hand: {name}")
    seen, unique = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            unique.append(it)
    return unique[:limit]
