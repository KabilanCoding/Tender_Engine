"""Single source of truth for criterion operators (used by the LLM extractor and PostValidator)."""
import re

# Plain comparison operators plus the set/period operators the extraction prompt may emit.
# Evaluated by the rule engine (step 7); anything outside this set is mapped or rejected.
ALLOWED_OPERATORS = {
    ">=", "<=", "==", "!=", ">", "<", "in", "contains", "not_in",
    "SUBMITTED", "OR", "AND",
    "ANY_OF", "ALL_OF", "WITHIN_LAST_N_FINANCIAL_YEARS",
}

# Free-text operators LLMs tend to produce -> canonical operator.
# ">" and "<" are intentionally NOT mapped to ">=" / "<=": strict inequality changes the verdict.
OPERATOR_MAP = {
    "active": "==", "built-in": "==", "is": "==", "enabled": "==", "true": "==", "yes": "==",
    "equal": "==", "equals": "==", "=": "==", "!": "!=", "not equal": "!=",
    "has": "contains", "with": "contains", "includes": "contains", "including": "contains",
    "features": "contains", "feature": "contains", "support": "contains", "supports": "contains",
    "at least": ">=", "min": ">=", "minimum": ">=", "greater than or equal": ">=",
    "at most": "<=", "max": "<=", "maximum": "<=", "less than or equal": "<=",
    "submitted": "SUBMITTED",
    "\u2265": ">=", "=>": ">=", ">=": ">=", "gte": ">=", "ge": ">=", "greater than or equals": ">=", "more than or equal": ">=",
    "not less than": ">=", "no less than": ">=", "at the least": ">=", "minimum of": ">=", "min.": ">=", "or above": ">=",
    "and above": ">=", "or more": ">=", "or higher": ">=", "above": ">=", "more than": ">", "greater than": ">",
    "exceeds": ">", "exceeding": ">", "\u2264": "<=", "=<": "<=", "lte": "<=", "le": "<=", "not more than": "<=",
    "not exceeding": "<=", "no more than": "<=", "up to": "<=", "upto": "<=", "or less": "<=", "or below": "<=",
    "less than": "<", "lt": "<", "below": "<", "under": "<", "gt": ">",
    "any_of": "ANY_OF", "any of": "ANY_OF", "all_of": "ALL_OF", "all of": "ALL_OF",
    "within_last_n_financial_years": "WITHIN_LAST_N_FINANCIAL_YEARS",
}


def canonical_operator(raw: object, value: object = None) -> str:
    """Return a canonical operator for `raw`; unknown operators fall back to contains/==."""
    op = str(raw if raw is not None else "==").strip()
    if op in ALLOWED_OPERATORS:
        return op
    mapped = OPERATOR_MAP.get(op.lower())
    if mapped:
        return mapped
    if op.upper() in ALLOWED_OPERATORS:
        return op.upper()
    low = op.lower()
    if re.search(r"(not|no|at)\s+(the\s+)?less|at\s+least|\bminimum\b|\bmin\b", low):
        return ">="                                  # "not less than 10" is a floor, whatever words follow
    if re.search(r"(not|no)\s+(more|greater)|at\s+most|\bmaximum\b", low):
        return "<="
    if re.search(r"more than|greater than|exceed(s|ing)?\s+\d|above\s+\d", low) and "or" not in low.split("than")[-1][:4]:
        return ">"
    if re.search(r"less|max|below|under|upto|up to|exceed.*not|\bat most\b", low):
        return "<="
    if re.search(r"least|\bmin|above|more|greater|higher|exceed", low):
        return ">="
    return "contains" if (isinstance(value, list) or "," in str(value)) else "=="
