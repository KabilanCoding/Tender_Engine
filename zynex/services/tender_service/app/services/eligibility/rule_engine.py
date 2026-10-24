"""Deterministic evaluation of extracted criteria against CompanyFacts.

Statuses:
  PASS           company record satisfies the requirement
  FAIL           a recorded company value violates the requirement (or a certificate is expired)
  MISSING        the knowledge base holds no data to decide; never guessed
  NEEDS_REVIEW   cannot be decided automatically (e.g. quote not verified, client type unknown)
  INFORMATIONAL  not a company attribute (fees, deadlines, submission mechanics)

The engine never fabricates company data: absence of data is MISSING, not FAIL and not PASS.
"""
import re
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.schemas import field_ontology
from app.schemas.eligibility import CriterionResultSchema, CriterionSchema
from app.services.eligibility.company_facts import CompanyFacts
from app.services.eligibility.multilingual import is_latin
from app.services.eligibility.domain_vocab import canonical_tech, text_has_domain
from app.services.eligibility.normalizer import Normalizer

Outcome = Tuple[str, Any, str]  # (status, company_value, evidence)

_DOC_FIELDS = {
    v.field_id for v in vars(field_ontology).values()
    if isinstance(v, field_ontology.FieldDef) and v.group == "Document Checklist"
} | {"completion_certificate", "performance_certificate", "solvency_certificate_val"}
_INFORMATIONAL_FIELDS = {
    "emd_amount", "tender_fee", "bid_validity_days", "submission_deadline", "dsc_required",
    "two_cover_submission", "submission_portal", "msme_category", "msme_udyam", "payment_terms",
}
_UNRECORDED_FIELDS = {  # facts the knowledge base does not hold yet
    "gst_registration": "GST registration is not recorded in the knowledge base.",
    "pan_card": "PAN is not recorded in the knowledge base.",
    "epf_registration": "EPF registration is not recorded in the knowledge base.",
    "esi_registration": "ESI registration is not recorded in the knowledge base.",
    "insolvency_status": "Insolvency / bankruptcy status is not recorded; a signed declaration is needed.",
    "company_website": "The company website is not recorded in the knowledge base.",
    "net_worth": "Net worth is not recorded in the knowledge base.",
    "working_capital": "Working capital is not recorded in the knowledge base.",
    "profit_after_tax": "Profit after tax by year is not recorded in the knowledge base.",
    "experience_years": "Years in business is not recorded in the knowledge base.",
    "blacklisted": "Blacklisting/debarment status is not recorded; a signed declaration is needed.",
    "incorporation_type": "Incorporation type is not recorded in the knowledge base.",
    "gst_registration": "GST registration is not recorded in the knowledge base.",
    "pan_card": "PAN is not recorded in the knowledge base.",
    "epf_registration": "EPF registration is not recorded in the knowledge base.",
    "esi_registration": "ESI registration is not recorded in the knowledge base.",
    "state_office": "Office locations are not recorded in the knowledge base.",
}
_CERT_FIELDS = {"certifications", "iso_9001", "iso_20000", "iso_27001", "cmmi_level", "cert_validity"}
_TECH_FIELDS = {"security_controls", "os_db_requirement"}
_NUMERIC_OPS = {">=", "<=", ">", "<", "==", "!="}
_ANY_OPS = {"ANY_OF", "OR"}
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


# ---------------------------------------------------------------- helpers
def _as_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value if value is not None else "").strip()
    if not text:
        return []
    return [p.strip() for p in re.split(r"[,;]|\band\b|\bor\b|\n", text) if p.strip()]


def _num(value: Any) -> Optional[float]:
    if isinstance(value, (list, tuple)):
        value = value[0] if len(value) == 1 else None      # a list of several values is not one threshold
    return Normalizer.parse_numeric(value)


_RELATIVE = re.compile(r"\d\s*%|\bper\s*cent|\bpercent|\btimes\s+(?:the|of)\b", re.IGNORECASE)
_MINIMUM_WORDS = re.compile(r"\bminimum\b|\bnot\s+less\s+than\b|\bat\s+least\b|\bor\s+(?:above|more|higher)\b|\band\s+above\b",
                            re.IGNORECASE)


_ZERO_OK_FIELDS = {"net_worth", "profit_after_tax", "working_capital"}


def _threshold(c: CriterionSchema) -> Tuple[Optional[float], str, str]:
    """(required number, operator, problem) for a numeric criterion. A requirement expressed relative to the
    tender's own value ('30% of the estimated cost') or a '==' on a threshold cannot be decided automatically."""
    value_text = str(c.value)
    if _RELATIVE.search(value_text) or (_RELATIVE.search(c.source_text or "") and
                                        not re.search(r"crore|lakh|lac|rs\.?|inr|₹|\d{5,}", value_text, re.I)):
        return None, c.operator, "The requirement is a percentage/multiple of the tender value, which is not known to the system."
    required = _num(c.value)
    if required is None:
        return None, c.operator, "The required value could not be read."
    if required == 0 and c.operator in (">=", "==", "<=") and c.field not in _ZERO_OK_FIELDS:
        return None, c.operator, "The tender gives no usable amount (the value read is 0); please check its wording."
    op = c.operator
    if op == "==":
        if _MINIMUM_WORDS.search(c.source_text or "") or _MINIMUM_WORDS.search(value_text):
            op = ">="
        else:
            return None, op, "The tender asks for an exact amount, which is unusual; please check its wording."
    return required, op, ""


def _completed_fy(today: Optional[date] = None) -> int:
    """End year of the last completed Indian financial year (Apr-Mar): on 2025-12-01 that is 2025 (FY2024-25)."""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def _tender_fy_years(source: str) -> List[int]:
    """FY end years named in the tender text: '2020-21, 2021-22' -> [2021, 2022]."""
    years = []
    for a, b in re.findall(r"\b((?:19|20)\d{2})\s*[-–/]\s*(\d{2}|(?:19|20)\d{2})\b", source):
        start = int(a)
        end = int(b) if len(b) == 4 else (start // 100) * 100 + int(b)
        if end == start + 1:
            years.append(end)
    return sorted(set(years))


def _fy_window(source: str, n: int) -> List[int]:
    """The N financial years the tender means: those it names, else the last N completed ones."""
    named = _tender_fy_years(source)
    if len(named) >= n:
        return named[-n:]
    last = _completed_fy()
    return list(range(last - n + 1, last + 1))


def _fy(y: int) -> str:
    return f"FY{y - 1}-{str(y)[2:]}"


def _compare(op: str, actual: float, required: float) -> bool:
    return {">=": actual >= required, "<=": actual <= required, ">": actual > required,
            "<": actual < required, "==": actual == required, "!=": actual != required}[op]


def _fmt_money(v: float) -> str:
    if v >= 1e7:
        return f"{v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"{v / 1e5:.2f} L"
    return f"{v:,.0f}"


_CERT_TAIL = re.compile(r"\bor\s+(?:higher|above|later|latest|equivalent|newer)\b|\b(?:latest|valid|current)\s+version\b",
                        re.IGNORECASE)


def _cert_key(name: str) -> str:
    """'ISO 9001:2015 (QMS)' / 'iso_9001' / 'ISO/IEC 20000-1:2018' -> 'iso9001' / 'iso20000'."""
    s = re.sub(r"\(.*?\)", "", str(name).lower())
    s = re.sub(r"\b(?:valid|current|latest|updated|certified|accredited|holding|having|a|an|the)\b", " ", s)   # 'Valid ISO 9001:2015 certification'
    s = _CERT_TAIL.sub("", s)
    s = re.sub(r"\b(?:certification|certificate|certificates|certifications)\b", " ", s)   # 'ISO 9001 certification'
    s = re.sub(r"[\s/]*\biec\b", "", s)                    # "ISO/IEC 27001" == "ISO 27001"
    s = re.sub(r"[:\s-]*(?<!\d)(?:19|20)\d{2}(?!\d)", "", s)  # drop year suffixes ':2015'
    s = re.sub(r"(\d{4,5})\s*-\s*\d\b", r"\1", s)        # part number: '20000-1' == '20000'
    return re.sub(r"[^a-z0-9]", "", s)


_GENERIC_CERT_WORDS = {"iso", "isoiec", "cert", "certificate", "certification", "certifications", "licence", "license", "registration"}


def _cert_matches(required_key: str, recorded_name: str) -> bool:
    """A recorded certificate matches when it is the required standard, optionally followed by a description
    ('ISO 27001:2022 Information Security Management' holds 'ISO 27001'). The next character after the number
    must not be a digit, so 'ISO 2000' never matches 'ISO 20000'."""
    held = _cert_key(recorded_name)
    if held == required_key:
        return True
    if required_key in _GENERIC_CERT_WORDS or len(required_key) < 4:
        return False                        # 'ISO' or 'certificate' alone names no standard: never match by prefix
    return held.startswith(required_key) and not held[len(required_key)].isdigit()


def _cmmi_level(text: str) -> Optional[int]:
    """'CMMI Level 3', 'CMMI ML3', 'CMMI V2.0 Level 5' -> 3, 3, 5 (the model version is not the level)."""
    t = text.lower()
    if "cmmi" not in t:
        return None
    m = re.search(r"(?:maturity\s+level|level|ml)\s*[-:]?\s*([1-5])\b", t) or \
        re.search(r"cmmi(?:\s*-?\s*(?:dev|svc|acq))?\s*[-:]?\s*([1-5])\b(?!\.\d)", t)
    return int(m.group(1)) if m else None


_NOT_A_CERT_NAME = {"yes", "no", "true", "false", "n/a", "na", "nil", "none", "applicable", "as applicable", "not applicable", "provided", "attached"}


def _cert_names(c: CriterionSchema) -> List[str]:
    """Required certificate names; a numeric/boolean value on a specific field is named after the field."""
    v = c.value
    if c.field == "cmmi_level" and (isinstance(v, (int, float)) and not isinstance(v, bool) or
                                    (isinstance(v, str) and re.fullmatch(r"\s*(?:level\s*)?[1-5]\s*", v, re.I))):
        return [f"CMMI Level {str(v).strip().split()[-1]}"]
    if c.field.startswith("iso_") and (isinstance(v, bool) or v in (None, "", "true", "True", "yes")):
        return ["ISO " + c.field.split("_", 1)[1]]
    text_items = v if isinstance(v, (list, tuple, set)) else [v]
    names: List[str] = []
    for item in text_items:
        text = _CERT_TAIL.sub("", str(item if item is not None else ""))
        text = re.sub(r"\b(iso\s*)(\d{4,5})\s*/\s*(\d{4,5})\b", r"\1\2, ISO \3", text, flags=re.I)  # ISO 9001/14001
        names += [p.strip() for p in re.split(r"[,;&+]|\band\b|\bor\b|\n", text, flags=re.I) if p.strip()]
    return [n for n in names if re.search(r"[a-z]", n, re.I) and n.strip().lower() not in _NOT_A_CERT_NAME]


def _tech_match(required: str, have: str) -> bool:
    """The required technology must appear as whole words inside a recorded skill ('python' in 'python 3.11');
    a generic skill ('linux') does not satisfy a longer requirement ('Red Hat Enterprise Linux 8')."""
    a, b = canonical_tech(required), canonical_tech(have)
    if not a or not b:
        return False
    # generic words and version numbers do not change what the technology is ('React JS' == 'react')
    a = re.sub(r"\.js\b|\b(?:js|framework|library|platform|technology|technologies|language|latest|version|"
               r"v?\d+(?:\.\d+)*\+?)\b", " ", a)
    a = re.sub(r"\s+", " ", a).strip()
    if not a:
        return False
    def has(needle: str, hay: str) -> bool:
        return re.search(rf"(?<![a-z0-9+#]){re.escape(needle)}(?![a-z0-9+#])", hay) is not None
    return a == b or has(a, b)


def _any_n_of_m(source: str) -> Optional[Tuple[int, int]]:
    """(N, M) from 'in any three of the last five financial years'."""
    words = "|".join(_NUM_WORDS)
    num = rf"(\d+|{words})(?:\s*\(\s*\d+\s*\))?"
    m = re.search(rf"\bany\s+{num}\s+(?:(?:financial|fiscal|consecutive)\s+)?(?:years?\s+)?(?:out\s+)?of\s+(?:the\s+)?"
                  rf"(?:last|preceding|previous|past)\s+{num}", source.lower())
    if not m:
        return None
    to_i = lambda t: int(t) if t.isdigit() else _NUM_WORDS[t]
    return to_i(m.group(1)), to_i(m.group(2))


def _years_window(source: str) -> Optional[int]:
    """N from 'last three financial years' / 'preceding 5 years'; None when the text names no window."""
    m = re.search(r"(?:last|preceding|previous|past)\s+(\d+|" + "|".join(_NUM_WORDS) + r")(?:\s*\(\s*\d+\s*\))?\s+"
                  r"(?:consecutive\s+)?(?:completed\s+)?(?:audited\s+)?(?:financial\s+|fiscal\s+)?years?", source.lower())
    if not m:
        return None
    return int(m.group(1)) if m.group(1).isdigit() else _NUM_WORDS[m.group(1)]


# ---------------------------------------------------------------- handlers
def _turnover(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    if c.operator not in _NUMERIC_OPS:
        return "NEEDS_REVIEW", None, "Multi-year turnover rule needs manual review."
    required, op, problem = _threshold(c)
    if required is None:
        return "NEEDS_REVIEW", None, problem
    if not f.turnover_by_fy:
        return "MISSING", None, "No turnover records in the knowledge base."
    if not is_latin(c.source_text):
        # 'average of three years', 'in each year', 'any three of five' cannot be read in this language: never guess
        latest = max(f.turnover_by_fy)
        return "NEEDS_REVIEW", _fmt_money(f.turnover_by_fy[latest]), (
            f"The tender wording is not in English, so its averaging period was not interpreted. Recorded turnover for "
            f"{_fy(latest)}: {_fmt_money(f.turnover_by_fy[latest])}; required: {_fmt_money(required)}. Check the period manually.")
    src = c.source_text.lower()
    tb = f.turnover_by_fy
    n = _years_window(src)
    pair = _any_n_of_m(src)

    def missing_years(window: List[int]) -> List[str]:
        return [_fy(y) for y in window if y not in tb]

    if pair:
        need, span = pair
        window = _fy_window(c.source_text, span)
        met = [y for y in window if y in tb and _compare(op, tb[y], required)]
        absent = missing_years(window)
        basis = (f"{len(met)} of {_fy(window[0])} to {_fy(window[-1])} meet {_fmt_money(required)}; {need} needed")
        if len(met) >= need:
            return "PASS", f"{len(met)} of {span} years", basis + "."
        if len(met) + len(absent) >= need:
            return "MISSING", f"{len(met)} of {span} years", basis + f"; not recorded: {', '.join(absent)}."
        return "FAIL", f"{len(met)} of {span} years", basis + "."
    if n and re.search(r"\b(?:cumulative|aggregate|total|combined)\b", src):
        window = _fy_window(c.source_text, n)
        absent = missing_years(window)
        if absent:
            return "MISSING", None, f"Cumulative turnover needs {', '.join(absent)}, which are not recorded."
        total = sum(tb[y] for y in window)
        ok = _compare(op, total, required)
        return ("PASS" if ok else "FAIL"), _fmt_money(total), (f"Total turnover {_fmt_money(total)} for {_fy(window[0])} "
                                                             f"to {_fy(window[-1])} vs required {_fmt_money(required)}.")
    if "average" in src:
        n = n or 3
        window = _fy_window(c.source_text, n)
        absent = missing_years(window)
        if absent:
            return "MISSING", None, f"Average over {n} years needs {', '.join(absent)}, which are not recorded."
        actual = sum(tb[y] for y in window) / n
        basis = f"average of {_fy(window[0])} to {_fy(window[-1])}"
    elif n and n > 1 and re.search(r"\b(?:each|every|all)\b", src):
        window = _fy_window(c.source_text, n)
        absent = missing_years(window)
        failing = [y for y in window if y in tb and not _compare(op, tb[y], required)]
        if failing:
            lowest = min(tb[y] for y in failing)
            return "FAIL", _fmt_money(lowest), (f"Turnover in {', '.join(_fy(y) for y in failing)} is below "
                                                f"{_fmt_money(required)} (each of {n} years required).")
        if absent:
            return "MISSING", None, f"Requirement applies to each of {n} years; not recorded: {', '.join(absent)}."
        lowest = min(tb[y] for y in window)
        return "PASS", _fmt_money(lowest), (f"Turnover in each of {_fy(window[0])} to {_fy(window[-1])} "
                                            f"(lowest {_fmt_money(lowest)}) vs required {_fmt_money(required)}.")
    elif n and n > 1:
        # 'turnover of Rs 5 crore during the last three years': average? each year? the tender does not say
        return "NEEDS_REVIEW", None, (f"The tender names a {n}-year period without saying average, each year or "
                                      "total; check the exact wording.")
    else:
        named = _tender_fy_years(c.source_text)
        target = named[-1] if named else None
        if target is not None and target not in tb:
            return "MISSING", None, f"The tender asks for {_fy(target)}, which is not recorded."
        latest = target or max(tb)
        if target is None and latest < _completed_fy() - 1:
            return "MISSING", None, (f"Latest recorded turnover is {_fy(latest)}; the recent financial years are not "
                                     "recorded.")
        actual = tb[latest]
        basis = _fy(latest)
    ok = _compare(op, actual, required)
    return ("PASS" if ok else "FAIL"), _fmt_money(actual), f"Turnover {_fmt_money(actual)} ({basis}) vs required {_fmt_money(required)}."


_QUALIFIED_WORK = re.compile(r"\bsimilar\b|\blast\s+\w+(?:\s*\(\d+\))?\s+years|\bpreceding\b|\bpast\s+\w+\s+years|"
                             r"\beach\s+(?:costing|of\s+value|valued|having)|\bgovernment\b|\bpsu\b|\bcompleted\s+during\b",
                             re.IGNORECASE)


def _qualified_work(c: CriterionSchema) -> bool:
    """The work asked for is qualified (similar, recent, government...). Wording the engine cannot read counts as qualified."""
    return bool(_QUALIFIED_WORK.search(c.source_text or "")) or not is_latin(c.source_text)


_RECENT = re.compile(r"\b(?:last|past|preceding|previous|during\s+the\s+last)\s+(one|two|three|four|five|six|seven|\d+)\s*(?:\(\d+\)\s*)?"
                     r"(?:financial\s+)?years?\b", re.IGNORECASE)
_GOVT = re.compile(r"\bgovernment\b|\bgovt\b|\bpsu\b|\bpublic\s+sector\b|\bstate\s+or\s+central\b", re.IGNORECASE)
_SIMILAR = re.compile(r"\bsimilar\b", re.IGNORECASE)


def _apply_qualifiers(c: CriterionSchema, projects) -> Tuple[list, List[str], List[str]]:
    """Filter projects by what the tender qualifies them with, using dates and client type where the knowledge base
    holds them. Returns (projects that qualify, things still unchecked, what was applied).
    A project whose date / client type is not recorded is kept but the point is reported as unchecked: never guessed."""
    src = c.source_text or ""
    keep, unchecked, applied = list(projects), [], []
    m = _RECENT.search(src)
    if m:
        raw = m.group(1).lower()
        years = int(raw) if raw.isdigit() else _NUM_WORDS.get(raw, 0)
        if years:
            cutoff = date.today().replace(year=date.today().year - years)
            dated = [p for p in keep if p.completion_date]
            if len(dated) == len(keep):
                keep = [p for p in keep if p.completion_date >= cutoff]
                applied.append(f"completed since {cutoff.isoformat()}")
            else:
                unchecked.append("completion date")
    if _GOVT.search(src):
        known = [p for p in keep if p.is_government_client is not None]
        if len(known) == len(keep):
            keep = [p for p in keep if p.is_government_client]
            applied.append("government / PSU client")
        else:
            unchecked.append("client type")
    if _SIMILAR.search(src) and not _domains(c):
        unchecked.append("what counts as similar work")
    other = _QUALIFIED_WORK.search(src) and not (m or _GOVT.search(src) or _SIMILAR.search(src))
    if other or not is_latin(src):
        unchecked.append("the work qualification")
    return keep, unchecked, applied


class _Domains(list):
    """The work-type words of a criterion, plus the names of projects the knowledge-base index matched to them by meaning."""
    semantic: frozenset = frozenset()


_BY_MEANING = "the kind of work asked for"


def _domains(c: CriterionSchema) -> List[str]:
    d = _Domains((c.alignment or {}).get("domains") or [])
    d.semantic = frozenset((c.alignment or {}).get("semantic_projects") or [])
    if not d and d.semantic:
        d.append(_BY_MEANING)          # no work-type word in the tender: the meaning search alone defines the work type
    return d


def _in_domain(p, domains: List[str]) -> bool:
    semantic = getattr(domains, "semantic", ())
    if not domains:
        return not semantic or p.name in semantic       # no work-type word: the meaning search alone says which projects fit
    return text_has_domain(p.searchable_text, domains) or p.name in semantic


def _by_meaning_only(p, domains: List[str]) -> bool:
    """Matched to the work type only by the meaning index (no domain word in its text): a likely match, not a sure one."""
    semantic = getattr(domains, "semantic", ())
    if p.name not in semantic:
        return False
    return not domains or not text_has_domain(p.searchable_text, domains)


def _names(projects, limit: int = 3) -> str:
    shown = "; ".join(f"{p.name} ({_fmt_money(p.value)})" if p.value else p.name for p in projects[:limit])
    return shown + ("; \u2026" if len(projects) > limit else "")


_TIER = re.compile(
    r"\b(one|two|three|four|five|\d+)\s+(?:similar\s+)?(?:works?|projects?|orders?|assignments?)\b[^.\n]{0,80}?"
    r"(?:not\s+less\s+than|at\s+least|minimum(?:\s+of)?|of\s+value)\s*(?:rs\.?|inr|\u20b9)?\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?)?",
    re.IGNORECASE)


def _tiers(text: str) -> List[Tuple[int, float]]:
    """[(number of works, minimum value of each)] from 'One work not less than Rs. 268.80 Cr. or Two works, each not
    less than Rs. 168 Cr. or Three works, each not less than Rs. 134.40 Cr.'"""
    out = []
    for m in _TIER.finditer(text or ""):
        n = int(m.group(1)) if m.group(1).isdigit() else _NUM_WORDS.get(m.group(1).lower(), 0)
        value = Normalizer.parse_numeric(f"{m.group(2)} {m.group(3) or ''}")
        if n and value:
            out.append((n, value))
    return out if len(out) >= 2 else []


def _tiered_work(c: CriterionSchema, f: CompanyFacts, tiers: List[Tuple[int, float]]) -> Outcome:
    domains = _domains(c)
    done = [p for p in f.completed_projects if p.value and _in_domain(p, domains)]
    shown = " or ".join(f"{n} work(s) of at least {_fmt_money(v)} each" for n, v in tiers)
    if not f.completed_projects:
        return "MISSING", None, "No completed projects recorded in the knowledge base."
    values = sorted((p.value for p in done), reverse=True)
    met = [(n, v) for n, v in tiers if len([x for x in values if x >= v]) >= n]
    best = _fmt_money(values[0]) if values else "none recorded"
    if not met:
        every = sorted((p.value for p in f.completed_projects if p.value), reverse=True)
        if every and any(len([x for x in every if x >= v]) >= n for n, v in tiers):
            return "NEEDS_REVIEW", best, f"Required: {shown}. Only projects not described as {' / '.join(domains)} reach this; confirm manually."
        return "FAIL", best, f"Required: {shown}. Largest recorded completed project: {best}; no alternative is reached."
    n, v = met[0]
    return "NEEDS_REVIEW", best, (f"Required: {shown}. The alternative of {n} work(s) of at least {_fmt_money(v)} is reached by "
                                  f"recorded projects; completion date and client type are not recorded; confirm manually.")


def _domain_experience(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    """Experience asked for as a list of work types ('IVRS / web portal / mobile application') with no number."""
    domains = _domains(c)
    done = f.completed_projects
    if not done:
        return "MISSING", None, "No completed projects recorded in the knowledge base."
    if not domains:
        return "NEEDS_REVIEW", None, "The experience asked for could not be read as a number of projects or a value; check manually."
    matching = [p for p in done if _in_domain(p, domains)]
    if not matching:
        return "NEEDS_REVIEW", None, f"No recorded completed project is described as {' / '.join(domains)}; confirm manually."
    return "NEEDS_REVIEW", len(matching), (f"{len(matching)} completed project(s) are described as {' / '.join(domains)}: "
                                          f"{_names(matching)}. Client type, dates and scope are not recorded; confirm manually.")


_LEADING_COUNT = re.compile(r"^\W*(one|two|three|four|five|\d+)\s+(?:similar\s+)?(?:works?|projects?|orders?|assignments?)\b", re.IGNORECASE)


def _leading_count(text: str) -> int:
    m = _LEADING_COUNT.match(text or "")
    if not m:
        return 1
    raw = m.group(1).lower()
    return int(raw) if raw.isdigit() else _NUM_WORDS.get(raw, 1)


def _project_value(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    tiers = _tiers(c.source_text)
    if tiers and (c.operator not in _NUMERIC_OPS or isinstance(c.value, (list, tuple))):
        return _tiered_work(c, f, tiers)
    if c.operator not in _NUMERIC_OPS:
        return _domain_experience(c, f)
    required, op, problem = _threshold(c)
    if required is None:
        return "NEEDS_REVIEW", None, problem
    values = [p.value for p in f.completed_projects if p.value]
    if not values:
        return "MISSING", None, "No completed projects with a recorded value."
    best = max(values)
    ok = _compare(op, best, required)
    msg = f"Largest completed project {_fmt_money(best)} vs required {_fmt_money(required)}."
    if not ok:
        return "FAIL", _fmt_money(best), msg                  # not even the largest project reaches it
    domains = _domains(c)
    reaching = sorted((p for p in f.completed_projects if p.value and _compare(op, p.value, required)), key=lambda p: -p.value)
    in_domain = [p for p in reaching if _in_domain(p, domains)]
    label = " / ".join(domains)
    need = _leading_count(c.source_text)
    if need > 1:                                  # 'Two similar works, each of at least X'
        have = len(in_domain if domains else reaching)
        if have < need:
            if len(reaching) >= need and domains:
                return "NEEDS_REVIEW", _fmt_money(best), msg + f" {need} works of this value are needed; only {have} are described as {label}; confirm manually."
            return "FAIL", _fmt_money(best), msg + f" {need} works of at least {_fmt_money(required)} each are needed; {len(reaching)} recorded."
    if domains and not in_domain:
        # the value is reached, but only by projects the knowledge base does not describe as this kind of work
        return "NEEDS_REVIEW", _fmt_money(best), (msg + f" None of the {len(reaching)} project(s) at this value is described as {label}"
                                                  f" ({_names(reaching)}); confirm that one of them qualifies.")
    shown = in_domain if domains else reaching
    msg += f" {len(shown)} project(s) {'in ' + label + ' ' if domains else ''}reach this value: {_names(shown)}."
    loose = [p for p in shown if _by_meaning_only(p, domains)]
    if loose:
        why = (c.alignment or {}).get("semantic_reasons") or {}
        reasons = "; ".join(f"{p.name}: {why[p.name]}" for p in loose if why.get(p.name))
        return "NEEDS_REVIEW", _fmt_money(best), msg + (f" {_names(loose)} look related by meaning only (the text does not say "
                                                        f"{label}); confirm they count." + (f" Reason: {reasons}." if reasons else ""))
    if _qualified_work(c):
        qualified, unchecked, applied = _apply_qualifiers(c, shown)
        if applied:
            msg += f" After checking {' and '.join(applied)}: {len(qualified)} qualify" + (f" ({_names(qualified)})." if qualified else ".")
        if len(qualified) < need:
            if unchecked:
                return "NEEDS_REVIEW", _fmt_money(best), msg + f" Not checked: {', '.join(unchecked)}; confirm manually."
            return "FAIL", _fmt_money(best), msg + f" {need} qualifying work(s) needed."
        if unchecked:
            return "NEEDS_REVIEW", _fmt_money(best), msg + f" Not recorded or not checkable: {', '.join(unchecked)}; confirm manually."
        return "PASS", _fmt_money(best), msg
    return "PASS", _fmt_money(best), msg


def _project_count(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    tiers = _tiers(c.source_text)
    if tiers and (c.operator not in _NUMERIC_OPS or isinstance(c.value, (list, tuple))):
        return _tiered_work(c, f, tiers)
    if c.operator not in _NUMERIC_OPS:
        return _domain_experience(c, f)
    required, op, problem = _threshold(c)
    if required is None:
        return "NEEDS_REVIEW", None, problem
    done = f.completed_projects
    n = len(done)
    if n == 0:
        return "MISSING", None, "No completed projects recorded in the knowledge base."
    ok = _compare(op, n, required)
    msg = f"{n} completed projects recorded vs required {int(required)}."
    if not ok:
        return "FAIL", n, msg
    domains = _domains(c)
    if domains:
        matching = [p for p in done if _in_domain(p, domains)]
        loose = [p for p in matching if _by_meaning_only(p, domains)]
        if loose and _compare(op, len(matching) - len(loose), required) is False:
            return "NEEDS_REVIEW", n, msg + (f" {len(loose)} of the matching projects look related by meaning only "
                                             f"({_names(loose)}); confirm they count.")
        if not _compare(op, len(matching), required):
            return "NEEDS_REVIEW", n, (msg + f" Only {len(matching)} of them {'is' if len(matching) == 1 else 'are'} described as "
                                       f"{' / '.join(domains)}; confirm that enough of the others qualify.")
        msg += f" {len(matching)} are described as {' / '.join(domains)}: {_names(matching)}."
    if c.field == "govt_psu_experience" or _qualified_work(c):
        pool = [p for p in done if _in_domain(p, domains)]
        if c.field == "govt_psu_experience" and not _GOVT.search(c.source_text or ""):
            c = c.model_copy(update={"source_text": (c.source_text or "") + " government"})
        qualified, unchecked, applied = _apply_qualifiers(c, pool)
        if applied:
            msg += f" After checking {' and '.join(applied)}: {len(qualified)} qualify" + (f" ({_names(qualified)})." if qualified else ".")
        if not _compare(op, len(qualified), required):
            if unchecked:
                return "NEEDS_REVIEW", n, msg + f" Not checked: {', '.join(unchecked)}; confirm manually."
            return "FAIL", len(qualified), msg + f" {int(required)} qualifying project(s) needed."
        if unchecked:
            return "NEEDS_REVIEW", n, msg + f" Not recorded or not checkable: {', '.join(unchecked)}; confirm manually."
        return "PASS", len(qualified), msg
    return "PASS", n, msg


_TOTAL_STAFF = re.compile(r"\b(?:employees|staff|manpower|workforce|headcount|payroll|personnel)\b", re.IGNORECASE)
_ROLE_WORDS = re.compile(r"certified|qualified|engineer|developer|professional|expert|architect|manager|analyst|"
                         r"specialist|consultant|tester|\bdegree\b|\bb\.?\s?e\b|\bb\.?\s?tech\b|\bmca\b|experience|"
                         r"\bcissp\b|\bpmp\b|\bcisa\b|\bcisco\b", re.IGNORECASE)

# kinds of job a tender names, and the words an employee record uses for them
_ROLE_KINDS = {
    "project manager": r"project manager|programme manager|program manager|delivery manager|project management|\bpm\b",
    "team lead": r"team[- ](?:lead|leader|head)|technical lead|tech lead|project lead|delivery head|head of|lead engineer",
    "business analyst": r"business analyst|systems? analyst|\bba\b|requirements? analyst",
    "solution architect": r"(?:solution|software|system|systems|enterprise|technical|lead|cloud|security|data|application)s?\s+architect",
    "developer": r"developer|programmer|software engineer|full[- ]?stack|back[- ]?end|front[- ]?end|java|python|\.net",
    "database administrator": r"\bdba\b|database administrator|database|dba",
    "devops engineer": r"devops|site reliability|\bsre\b|cloud engineer|infrastructure|systems? administrator",
    "tester": r"\bqa\b|tester|quality assurance|test engineer|testing",
    "security expert": r"security|cissp|\bceh\b|cyber|soc analyst|infosec|isms",
    "ui/ux designer": r"\bui\b|\bux\b|designer",
}
_ROLE_KIND_RE = {k: re.compile(v, re.IGNORECASE) for k, v in _ROLE_KINDS.items()}
_YEARS_IN_TEXT = re.compile(r"(?:at\s+least|minimum(?:\s+of)?|not\s+less\s+than|more\s+than)?\s*(\d{1,2})\s*(?:\+\s*)?(?:\(\w+\)\s*)?years?", re.IGNORECASE)


def _role_kinds_in(text: str) -> List[str]:
    return [k for k, rx in _ROLE_KIND_RE.items() if rx.search(text or "")]


def _semantic_people(c: CriterionSchema) -> frozenset:
    return frozenset((c.alignment or {}).get("semantic_employees") or [])


def _people_for(c: CriterionSchema, f: CompanyFacts, kinds: List[str]) -> Tuple[list, list]:
    """(employees whose record names the required job, those found only by the meaning search)."""
    by_words = [e for e in f.employees if any(_ROLE_KIND_RE[k].search(e.profile_text) for k in kinds)] if kinds else []
    seen = {e.name for e in by_words}
    by_meaning = [e for e in f.employees if e.name in _semantic_people(c) and e.name not in seen]
    return by_words, by_meaning


def _person(e) -> str:
    return f"{e.name} ({e.role}" + (f", {e.experience_years:g} yrs" if e.experience_years else "") + ")"


def _roles_by_record(c: CriterionSchema, f: CompanyFacts) -> Optional[Outcome]:
    """Experience / qualification of the people for a named job, read from the employee records. None = cannot decide here."""
    text = c.source_text or ""
    kinds = _role_kinds_in(text)
    if c.field == "role_experience_years":
        required, op, _ = _threshold(c) if c.operator in _NUMERIC_OPS else (None, c.operator, "")
        if required is None:
            return None
        pool, loose = _people_for(c, f, kinds)
        if not pool and not loose:
            return None
        known = [e for e in pool if e.experience_years is not None]
        meeting = [e for e in known if _compare(op, e.experience_years, required)]
        if meeting and kinds:
            return "PASS", len(meeting), (f"{len(meeting)} employee(s) recorded as {' / '.join(kinds)} have at least {required:g} years: "
                                          + "; ".join(_person(e) for e in meeting[:3]) + ".")
        if known and not meeting and kinds and not loose:
            best = max(e.experience_years for e in known)
            return "FAIL", f"{best:g} years", (f"Recorded {' / '.join(kinds)}: " + "; ".join(_person(e) for e in known[:3])
                                               + f". None has the {required:g} years required.")
        reach = [e for e in loose if e.experience_years is not None and _compare(op, e.experience_years, required)]
        if reach:
            return "NEEDS_REVIEW", len(reach), (f"Related by meaning only (no recorded job title for it): "
                                                + "; ".join(_person(e) for e in reach[:3]) + f"; each has at least {required:g} years. Confirm they fit the role.")
        return None
    if c.field == "role_qualification":
        degrees = [str(x).strip() for x in (c.value if isinstance(c.value, (list, tuple)) else [c.value]) if _DEGREE.search(str(x))]
        if not degrees:
            return None
        pool, loose = _people_for(c, f, kinds)
        pool = pool or ([e for e in f.employees] if not kinds else [])
        qual = [e for e in pool if e.qualification and any(_degree_core(d) in e.qualification.lower() for d in degrees)]
        if qual and kinds:
            return "PASS", len(qual), (f"{len(qual)} employee(s) recorded as {' / '.join(kinds)} hold {' / '.join(degrees[:3])}: "
                                       + "; ".join(_person(e) for e in qual[:3]) + ".")
        if qual:
            return "NEEDS_REVIEW", len(qual), (f"{len(qual)} employee(s) hold {' / '.join(degrees[:3])} (e.g. {_person(qual[0])}); the tender's role "
                                               "could not be matched to a recorded job title; confirm.")
        return None
    return None


def _degree_core(text: str) -> str:
    """'B.E. (CSE)' / 'Degree in Engineering' -> a short lower-case token to look for in a recorded qualification."""
    t = re.sub(r"[^a-z.\s]", " ", text.lower())
    for token in ("b.e", "b.tech", "m.tech", "mca", "bca", "msc", "m.sc", "bsc", "b.sc", "mba", "diploma", "ph.d", "engineering"):
        if token in t.replace(" ", ""):
            return token
    return t.strip()[:12] or text.lower()



def _employees(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    if c.operator not in _NUMERIC_OPS:
        return "NEEDS_REVIEW", None, "Required headcount could not be parsed."
    required, op, problem = _threshold(c)
    if required is None:
        return "NEEDS_REVIEW", None, problem
    if f.employee_count is None:
        return "MISSING", None, "No employee records in the knowledge base."
    ok = _compare(op, f.employee_count, required)
    msg = f"{f.employee_count} active employees vs required {int(required)}."
    if not ok and op in (">=", ">"):
        return "FAIL", f.employee_count, msg      # fewer people in total than the tender asks for in any role
    src = c.source_text or ""
    if _ROLE_WORDS.search(src) or not _TOTAL_STAFF.search(src):
        kinds = _role_kinds_in(src)
        if kinds and f.employees:
            counts = {k: len(_people_for(c, f, [k])[0]) for k in kinds}
            absent = [k for k, n in counts.items() if n == 0]
            shown = ", ".join(f"{k} ({n})" for k, n in counts.items())
            if absent:
                return "MISSING", f.employee_count, msg + f" No recorded employee for: {', '.join(absent)}. Recorded: {shown}."
            if not re.search(r"\d+\s*(?:\+\s*)?years?|degree|\bb\.?\s?e\b|\bmca\b|certified", src, re.IGNORECASE):
                return "PASS", f.employee_count, msg + f" Every role asked for has a recorded employee: {shown}."
            return "NEEDS_REVIEW", f.employee_count, msg + f" Every role asked for has a recorded employee ({shown}); the years / qualifications asked for are checked separately."
        return "NEEDS_REVIEW", f.employee_count, msg + " The roles/qualifications the tender asks for must be checked manually."
    return ("PASS" if ok else "FAIL"), f.employee_count, msg


def _certifications(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    required = _cert_names(c)
    if not required:
        return "NEEDS_REVIEW", None, "No certification named in the criterion."
    if not f.certifications:
        return "MISSING", None, "No certifications recorded in the knowledge base."

    found, expired, absent, unreadable, below = [], [], [], [], []
    for req in required:
        req_level = _cmmi_level(req)
        if req_level is not None:  # CMMI: a higher level also satisfies a lower requirement
            matches = [cf for cf in f.certifications if "cmmi" in cf.name.lower() and (_cmmi_level(cf.name) or 0) >= req_level]
            if not matches:
                lower = [cf for cf in f.certifications if "cmmi" in cf.name.lower() and _cmmi_level(cf.name)]
                if lower:                       # the company is appraised, but below the level the tender asks for
                    best = max(lower, key=lambda cf: _cmmi_level(cf.name) or 0)
                    below.append(f"{best.name} is below the required CMMI Level {req_level}")
                    continue
        else:
            key = _cert_key(req)
            matches = [cf for cf in f.certifications if key and _cert_matches(key, cf.name)]
        if not matches:
            absent.append(req)
            continue
        valid = [cf for cf in matches if not cf.is_expired() and not cf.validity_unreadable]
        if valid:
            found.append(valid[0].name)
        elif any(cf.validity_unreadable for cf in matches):
            bad = next(cf for cf in matches if cf.validity_unreadable)
            unreadable.append(f"{bad.name} (validity '{bad.raw_valid_until}')")
        else:
            latest = max(matches, key=lambda cf: cf.valid_until)
            expired.append(f"{latest.name} (expired {latest.valid_until})")

    if c.operator in _ANY_OPS:
        if found:
            return "PASS", ", ".join(found), f"Held: {', '.join(found)}."
        if expired and not absent and not unreadable:
            return "FAIL", ", ".join(expired), f"Every accepted certificate has expired: {', '.join(expired)}."
        if below and not found and not absent and not unreadable and not expired:
            return "FAIL", None, f"{'; '.join(below)}."
    elif expired:
        return "FAIL", ", ".join(expired), f"Certificate expired: {', '.join(expired)}."
    elif below:
        return "FAIL", ", ".join(found) or None, f"{'; '.join(below)}."
    if unreadable:
        return "NEEDS_REVIEW", ", ".join(found) or None, f"Validity date cannot be read: {', '.join(unreadable)}."
    if absent:
        held = ", ".join(cf.name for cf in f.certifications) or "none"
        return "MISSING", ", ".join(found) or None, f"Not found in knowledge base: {', '.join(absent)}. Recorded: {held}."
    return "PASS", ", ".join(found), f"Held: {', '.join(found)}."


def _technology(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    required = _as_list(c.value)
    if not required:
        return "NEEDS_REVIEW", None, "No technology named in the criterion."
    if not f.technologies:
        return "MISSING", None, "No technologies/skills recorded in the knowledge base."
    have = [r for r in required if any(_tech_match(r, t) for t in f.technologies)]
    if len(have) == len(required) or (c.operator in _ANY_OPS and have):
        return "PASS", ", ".join(have), f"Recorded capability for: {', '.join(have)}."
    lacking = [r for r in required if r not in have]
    return "MISSING", ", ".join(have) or None, f"No recorded capability for: {', '.join(lacking)}."


def _document(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    return "NEEDS_REVIEW", None, "Document must be prepared and submitted with the bid; its presence cannot be checked automatically."


def _unrecorded(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    return "MISSING", None, _UNRECORDED_FIELDS[c.field]


def _informational(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    return "INFORMATIONAL", None, "Procedural or financial term of the tender, not a company attribute."


_DEGREE = re.compile(r"\b(?:degree|graduate|post[- ]?graduate|engineer(?:ing)?\s+degree|b\.?\s?e\.?|b\.?\s?tech|m\.?\s?tech|mca|bca|msc|m\.?sc|bsc|b\.?sc|mba|diploma|ph\.?d|bachelor|master)\b", re.IGNORECASE)


def _roles(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    """Key-personnel requirements: which required roles have an active employee in the knowledge base. Years of
    experience and qualifications are not recorded per employee, so a fully staffed list still needs a person's check."""
    if not f.employees:
        return "MISSING", None, "No employee records in the knowledge base."
    decided = _roles_by_record(c, f)
    if decided is not None:
        return decided
    names = [str(x).strip() for x in (c.value if isinstance(c.value, (list, tuple)) else [c.value])
             if str(x).strip() and not re.fullmatch(r"[\d.\s]+", str(x))]
    if not names or c.field == "role_experience_years":
        return "NEEDS_REVIEW", f.employee_count, ("Years of experience and qualifications are not recorded per employee; "
                                                   "check the named personnel manually.")
    if all(_DEGREE.search(n) for n in names):
        return "NEEDS_REVIEW", f.employee_count, ("The tender names qualifications (" + ", ".join(names[:4])
                                                  + "); employees' qualifications are not recorded; check them manually.")
    recorded, absent = [], []
    for name in names:
        if _DEGREE.search(name):
            continue                              # a degree is checked by a person; only job roles are looked up
        key = name.lower()
        hits = [e for e in f.employees if key in f"{e.role} {' '.join(e.skills)}".lower()]
        (recorded if hits else absent).append((name, hits))
    if absent:
        return "MISSING", None, ("No active employee is recorded for: " + ", ".join(n for n, _ in absent)
                                 + (f". Recorded: {', '.join(f'{n} ({len(h)})' for n, h in recorded)}." if recorded else "."))
    return "NEEDS_REVIEW", len(recorded), ("Recorded for each role: " + ", ".join(f"{n} ({len(h)})" for n, h in recorded)
                                           + ". Qualifications and years of experience are not recorded per employee; confirm manually.")


# ── registration facts and balance-sheet figures (company_profile table, financial_records) ─────────────────────────
_PROFILE_KEYS = {"gst_registration": ("gstin", "GST registration"), "pan_card": ("pan", "PAN"),
                 "company_website": ("corporate_website", "Company website"),
                 "epf_registration": ("epf_registration", "EPF registration"), "esi_registration": ("esi_registration", "ESI registration")}
_FIN_SERIES = {"net_worth": ("net_worth_by_fy", "Net worth"), "working_capital": ("working_capital_by_fy", "Working capital"),
               "profit_after_tax": ("net_profit_by_fy", "Net profit")}
_COMPANY_KINDS = ("private limited", "public limited", "limited liability partnership", "llp", "partnership", "proprietor", "company")


_PLACEHOLDER = re.compile(r"(x{3,}|0{4,}|1234|abcde|\btest\b|\bsample\b|\bdummy\b|\bn/?a\b|\btbd\b)", re.I)


def looks_like_placeholder(value: str) -> bool:
    """Identifiers such as AABCX1234F or 33AABCX1234F1ZV are template values, never a confirmed fact."""
    return bool(_PLACEHOLDER.search(str(value or "")))


def _profile_fact(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    key, label = _PROFILE_KEYS[c.field]
    value = f.profile.get(key)
    if not value:
        return _unrecorded(c, f)
    if looks_like_placeholder(value):
        return "NEEDS_REVIEW", value, f"{label} on file ({value}) looks like a placeholder, not a real number; enter the real one in the Knowledge Base. [PLACEHOLDER_SUSPECTED]"
    if key in f.profile_sample:
        return "NEEDS_REVIEW", value, f"{label} is on file ({value}) but has not been verified yet; open it in the Knowledge Base, check it and save it."
    return "PASS", value, f"{label} is recorded: {value}."


def _incorporation(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    kind = f.profile.get("company_type")
    if not kind:
        return _unrecorded(c, f)
    wanted = [w.lower() for w in _as_list(c.value)]
    have = kind.lower()
    if any(w in have or have in w for w in wanted) or ("company" in have and any("compan" in w for w in wanted)):
        return "PASS", kind, f"The company is a {kind}."
    return "NEEDS_REVIEW", kind, f"The company is a {kind}; the tender names {', '.join(_as_list(c.value))}. Check that this type is accepted."


def _years_in_business(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    raw = f.profile.get("date_of_incorporation")
    inc = Normalizer.parse_date(raw) if raw else None
    if inc is None:
        return _unrecorded(c, f)
    years = (date.today() - inc).days / 365.25
    required, op, problem = _threshold(c) if c.operator in _NUMERIC_OPS else (None, c.operator, "")
    if required is None:
        return "NEEDS_REVIEW", f"{years:.0f} years", problem or "The required number of years could not be read."
    about = f"Incorporated {inc.isoformat()} ({years:.1f} years) vs required {required:g} years."
    if op in (">=", ">") and years < required:
        return "FAIL", f"{years:.0f} years", about + " The company is younger than that, so it cannot have more experience."
    if re.search(r"incorporat|existence|existing|in\s+business|registered|operat", c.source_text or "", re.IGNORECASE):
        return ("PASS" if _compare(op, years, required) else "FAIL"), f"{years:.0f} years", about
    return "NEEDS_REVIEW", f"{years:.0f} years", about + " The tender asks for experience in specific work, not company age; confirm from the project list."


def _office(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    places = [w for w in _as_list(c.value) if w.lower() not in ("true", "false", "office", "yes")]
    address = f.profile.get("registered_address")
    if not address and not f.offices:
        return _unrecorded(c, f)

    def at(text: str, place: str) -> bool:
        return bool(re.search(r"\b" + re.escape(place.lower()) + r"\b", text.lower()))

    confirmed, sample = [], []
    for o in f.offices:
        if any(at(f"{o.city} {o.state}", p) for p in places):
            (sample if o.is_sample else confirmed).append(f"{o.city}{', ' + o.state if o.state else ''} ({o.office_type or 'office'})")
    if address and "registered_address" not in f.profile_sample and any(at(address, p) for p in places):
        confirmed.append(f"registered office: {address}")
    if confirmed:
        return "PASS", "; ".join(confirmed), f"Office recorded in {', '.join(places) or 'the required place'}: {'; '.join(confirmed)}."
    if sample:
        return "NEEDS_REVIEW", "; ".join(sample), f"An office in {', '.join(places)} is on file but has not been verified yet ({'; '.join(sample)}); open it in the Knowledge Base, check it and save it."
    known = [f"{o.city}{', ' + o.state if o.state else ''}" for o in f.offices if not o.is_sample]
    where = ("; ".join(([f"registered office {address}"] if address else []) + known)) or "none"
    return "NEEDS_REVIEW", where, f"No recorded office in {', '.join(places) or 'the required place'}. Offices on file: {where}. Check whether a local office is needed at bid time."


_YES = ("yes", "true")


def _disqualification(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    """'Not blacklisted / not insolvent': decided only from a recorded answer, and never from a sample value."""
    keys = ("blacklisted", "debarred") if c.field == "blacklisted" else ("insolvency",)
    label = "blacklisted or debarred" if c.field == "blacklisted" else "under insolvency or liquidation proceedings"
    answers = {k: (f.profile.get(k) or "").strip().lower() for k in keys}
    if not answers[keys[0]]:
        return _unrecorded(c, f)
    if any(k in f.profile_sample for k in keys if answers[k]):
        return "NEEDS_REVIEW", answers[keys[0]], f"Whether the company is {label} is on file but has not been verified yet; open it in the Knowledge Base, check it and save it."
    if any(a in _YES for a in answers.values()):
        return "FAIL", "yes", f"The knowledge base records the company as {label}."
    missing = [k for k in keys if not answers[k]]
    note = f" ({', '.join(missing)} is not recorded.)" if missing else ""
    return "PASS", "no", f"The knowledge base records the company as not {label}.{note} Submit the signed declaration with the bid."


_OEM_RE = re.compile(r"\bOEM\b|original equipment|authori[sz]ed (?:partner|dealer|reseller|distributor|service)|manufacturer'?s? authori[sz]ation|\bMAF\b|partner(?:ship)? (?:certificate|letter)", re.IGNORECASE)
_CONSORTIUM_RE = re.compile(r"consortium|joint venture|\bJV\b|lead (?:bidder|member)|sub-?contract", re.IGNORECASE)


def _review(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    text = f"{c.source_text or ''} {c.value if isinstance(c.value, str) else ''}"
    if _OEM_RE.search(text):
        have = [f"{m.oem}{' – ' + m.product if m.product else ''}{' (not verified)' if m.is_sample else ''}" for m in f.oem_partners if (m.status or 'active').lower() != 'inactive']
        if have:
            return "NEEDS_REVIEW", "; ".join(have), f"OEM partnerships on file: {'; '.join(have)}. The authorisation letter for the product the tender names must be checked by a person."
        return "NEEDS_REVIEW", None, "No OEM partnership is recorded in the knowledge base; an authorisation letter from the maker may be needed."
    if _CONSORTIUM_RE.search(text):
        can = (f.profile.get("can_bid_as_consortium") or "").lower()
        lead = (f.profile.get("can_be_lead_bidder") or "").lower()
        sample = " (not yet verified)" if {"can_bid_as_consortium", "can_be_lead_bidder"} & f.profile_sample else ""
        if can or lead:
            return "NEEDS_REVIEW", can or None, f"Consortium bidding on file: can bid as consortium = {can or 'not recorded'}, can lead = {lead or 'not recorded'}{sample}. Check the tender's consortium rules."
    return "NEEDS_REVIEW", None, "This system has no automatic check for this requirement, so a person must check it."


def _financial_figure(c: CriterionSchema, f: CompanyFacts) -> Outcome:
    attr, label = _FIN_SERIES[c.field]
    series = getattr(f, attr)
    if not series:
        return _unrecorded(c, f)
    if c.operator not in _NUMERIC_OPS:
        return "NEEDS_REVIEW", None, f"{label} rule needs manual review."
    required, op, problem = _threshold(c)
    if required is None:
        return "NEEDS_REVIEW", None, problem
    named = _tender_fy_years(c.source_text or "")
    target = named[-1] if named else max(series)
    if target not in series:
        return "MISSING", None, f"The tender asks for {label.lower()} for {_fy(target)}, which is not recorded."
    if not named and target < _completed_fy() - 1:
        return "MISSING", None, f"Latest recorded {label.lower()} is for {_fy(target)}; the recent financial years are not recorded."
    ok = _compare(op, series[target], required)
    return ("PASS" if ok else "FAIL"), _fmt_money(series[target]), f"{label} {_fmt_money(series[target])} ({_fy(target)}) vs required {_fmt_money(required)}."


_FIELD_HANDLERS: Dict[str, Callable[[CriterionSchema, CompanyFacts], Outcome]] = {
    "annual_turnover": _turnover,
    "project_value": _project_value, "similar_work_value": _project_value,
    "contract_count": _project_count, "govt_psu_experience": _project_count,
    "team_role_count": _employees, "role_qualification": _roles, "role_experience_years": _roles,
    "cloud_ops_experience": lambda c, f: _review(c, f), "software_component_value": lambda c, f: _review(c, f),
}


class RuleEngine:
    @classmethod
    def evaluate(cls, criteria: List[CriterionSchema], facts: CompanyFacts) -> List[CriterionResultSchema]:
        return [cls._evaluate_one(c, facts) for c in criteria]

    @classmethod
    def _handler(cls, c: CriterionSchema):
        if c.field in _FIELD_HANDLERS:
            return _FIELD_HANDLERS[c.field]
        if c.field == "cert_validity":
            return _document                    # 'certificate must carry a valid UDIN / be current' is checked on the document
        if c.field in _PROFILE_KEYS:
            return _profile_fact
        if c.field in _FIN_SERIES:
            return _financial_figure
        if c.field == "incorporation_type":
            return _incorporation
        if c.field == "experience_years":
            return _years_in_business
        if c.field == "state_office":
            return _office
        if c.field in ("blacklisted", "insolvency_status"):
            return _disqualification
        if c.field in _CERT_FIELDS:
            return _certifications
        if c.field in _TECH_FIELDS:
            return _technology
        if c.field in _UNRECORDED_FIELDS:
            return _unrecorded                  # a fact the company must have; 'submit the URL' is only its proof
        if c.field in _DOC_FIELDS or c.operator == "SUBMITTED":
            return _document
        if c.field in _INFORMATIONAL_FIELDS:
            return _informational
        return _review

    @classmethod
    def _evaluate_one(cls, c: CriterionSchema, facts: CompanyFacts) -> CriterionResultSchema:
        handler = cls._handler(c)
        try:
            status, company_value, evidence = handler(c, facts)
        except Exception as e:  # a bad rule must never abort the whole evaluation
            status, company_value, evidence = "NEEDS_REVIEW", None, f"Rule error: {type(e).__name__}"

        if not c.exact_match and status in ("PASS", "FAIL"):
            # the quote was not found verbatim in the tender, so do not let it drive a verdict
            evidence = f"{evidence} (Tender quote could not be verified; confirm against the document.)"
            status = "NEEDS_REVIEW"

        return CriterionResultSchema(
            criterion_id=c.criterion_id, page_no=c.page_no, field=c.field, status=status,
            tender_value=c.value, company_value=company_value, mandatory=c.mandatory,
            source_text=c.source_text, operator=c.operator, section=c.section,
            grounded=c.exact_match, evidence=evidence,
            is_document=handler is _document, alignment=c.alignment, alt_group=c.alt_group, group=c.group,
        )
