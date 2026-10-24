import re
import unicodedata
import logging
from typing import List, Dict, Tuple, Any, Optional
from app.core.config import settings
from app.schemas.eligibility import CriterionSchema
from app.schemas.eligibility import ChunkSchema
from app.services.eligibility.errors import PipelineError
from app.services.eligibility.multilingual import is_latin
from app.services.eligibility.pipeline_log import log_pipeline_step
from app.schemas.field_ontology import canonicalize_field
from app.services.eligibility.operators import ALLOWED_OPERATORS, OPERATOR_MAP

try:
    from rapidfuzz import fuzz as _rfuzz

    def _partial_ratio(a: str, b: str) -> float:
        return _rfuzz.partial_ratio(a, b)   # 0-100
except ImportError:
    from difflib import SequenceMatcher

    def _partial_ratio(needle: str, haystack: str) -> float:
        """Fallback: share of `needle` found as matching blocks inside `haystack` (0-100).

        Plain SequenceMatcher.ratio() compares whole strings, so a short quote inside a long
        page scores near zero; measure coverage of the needle instead.
        """
        if not needle:
            return 0.0
        if needle in haystack:
            return 100.0
        blocks = SequenceMatcher(None, needle, haystack, autojunk=False).get_matching_blocks()
        return 100.0 * sum(b.size for b in blocks) / len(needle)

_near_miss_log: List[Dict] = []   # accessible for threshold tuning scripts

near_miss_logger = logging.getLogger("grounding.near_miss")

class _SettingValue:
    """Class attribute whose value is looked up in `settings` each time it is read."""

    def __init__(self, attr: str):
        self.attr = attr

    def __get__(self, obj, owner=None) -> float:
        return float(getattr(settings, self.attr))


_FIELD_EVIDENCE = {name: re.compile(rx, re.IGNORECASE) for name, rx in {
    "annual_turnover": r"turnover|revenue|income|sales",
    "net_worth": r"net\s*worth|networth",
    "working_capital": r"working\s*capital",
    "solvency_certificate_val": r"solven",
    "certifications": r"certif|\biso\b|cmmi|accredit|apprais|licen[cs]e|registration|empanel|complian|standard|\bcert\b",
    "blacklisted": r"black\s?list|debar|\bban|disqualif|corrupt|fraud|suspend|insolven|bankrupt|liquidat",
    "non_blacklisting_declaration": r"black\s?list|debar|\bban|declar|undertak|affidavit|self[- ]certif",
    "experience_years": r"experience|existen|operation|years?|business|incorporat|establish",
    "similar_work_value": r"work|project|order|contract|assignment|executed|completed|implement",
    "project_value": r"work|project|order|contract|assignment|executed|completed|implement",
    "contract_count": r"work|project|order|contract|assignment|executed|completed|implement",
    "team_role_count": r"team|employee|staff|personnel|engineer|developer|manpower|resource|professional|expert|member",
    "state_office": r"office|branch|presence|located|address|premises|cent(?:re|er)",
    "incorporation_type": r"compan|firm|partnership|proprietor|incorporat|registered|\bllp\b|society|trust|entity|legal\s+status|constitution",
    "letter_of_authorization": r"authori[sz]|power\s+of\s+attorney|\bpoa\b|mandate",
    "bid_validity_days": r"valid",
    "emd_amount": r"\bemd\b|earnest|bid\s+security|security\s+deposit|\bsd\b",
    "gst_registration": r"\bgst",
    "pan_card": r"\bpan\b",
    "insolvency_status": r"insolven|bankrupt|liquidat|solven",
}.items()}
_NUMBER_NOISE_FIELDS = {"bid_validity_days", "submission_deadline", "emd_amount", "tender_fee", "submission_portal"}
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90}


_REQUIREMENT_CUE = re.compile(
    r"\b(?:shall|must|should|require[sd]?|requirements?|at\s+least|minimum|not\s+less\s+than|no\s+less\s+than|"
    r"valid|hold|have|possess|submit|provide|furnish|maintain|demonstrat\w*|registered|eligib\w*|"
    r"qualif\w*|certified|enclose|attach|produce|mandatory|compulsory|exceed\w*|more\s+than|up\s*to|within)\b", re.IGNORECASE)
_STOP_WORDS = {"the", "a", "an", "of", "and", "or", "in", "to", "for", "at", "with", "on", "by", "is", "are", "be", "as",
               "from", "least", "than", "more", "less", "any", "all", "one", "per"}
# words a field id is usually written with in a tender (used when a field has no pattern of its own)
_FIELD_ALIASES = {"dsc": r"\bdsc\b|digital\s+signature", "rpo": r"\brpo\b|recovery\s+point", "rto": r"\brto\b|recovery\s+time",
                  "epf": r"\bepf|provident\s+fund", "esi": r"\besic?\b|state\s+insurance", "csp": r"\bcsp\b|cloud\s+service",
                  "msme": r"msme|micro|small\s+enterprise|udyam", "website": r"web\s?site|web\s+portal|\burl\b"}
_FIELD_ID_NOISE = {"required", "status", "type", "value", "count", "years", "amount", "number", "other", "details"}


_MAX_FUZZY_QUOTE = 1200
_FIELD_EXCLUDE = {"bid_validity_days": re.compile(r"\bemd\b|\bbg\b|bank\s+guarantee|performance\s+(?:bank\s+)?guarantee|earnest", re.IGNORECASE)}

# a threshold of these kinds is stated once however many pages repeat it (body, compliance form, annexure)
_SINGLE_THRESHOLD_FIELDS = {"annual_turnover", "net_worth", "working_capital", "profit_after_tax", "emd_amount", "tender_fee"}
_RELAXATION = re.compile(r"start[\s-]?ups?|\bksum\b|\bmsmes?\b|\bmses?\b|\bsmall\s+enterprise|relaxation|exempt", re.IGNORECASE)


def _field_gate(field: str):
    """Pattern the quote must match for `field`: its own pattern, else words taken from the field id."""
    if field in _FIELD_EVIDENCE:
        return _FIELD_EVIDENCE[field]
    parts = [w for w in field.split("_") if w and w not in _FIELD_ID_NOISE]
    if not parts or field == "other":
        return None
    return re.compile("|".join(_FIELD_ALIASES.get(w, re.escape(w[:5] if len(w) > 5 else w)) for w in parts), re.IGNORECASE)


def _words(text: Any) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", str(text or "")).lower()) if w not in _STOP_WORDS]


def value_support(value: Any, quote: Any) -> Optional[float]:
    """Share (0-1) of the wording of `value` that the quote actually contains; None when there is nothing to compare
    (a yes/no value or a plain number, which other checks cover). A model that copies a prompt example instead of
    reading the tender produces a value the quote never mentions."""
    if value is None or isinstance(value, (bool, int, float)):
        return None
    items = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
    quote_words = set(_words(quote))
    if not quote_words:
        return None
    scored = []
    for item in items:
        words = _words(item)
        if not words or all(w.isdigit() for w in words) and len(items) == 1 and len(words) == 1:
            continue
        hit = sum(1 for w in words if w in quote_words or (len(w) >= 5 and any(q.startswith(w[:5]) for q in quote_words)))
        scored.append(hit / len(words) >= 0.5)
    return (sum(scored) / len(scored)) if scored else None


class PostValidator:
    """
    S7 Post-Extraction Validator (hardened with fuzzy grounding).
    1. Validates criterion fields & allowed operators.
    2. Fuzzy grounding: NFKC + whitespace/dash fold + rapidfuzz partial_ratio.
       - >= GROUNDING_FUZZY_THRESHOLD (default 92): PASS, returns [start,end] span.
       - below threshold: exact_match=False, so the criterion is routed to NEEDS_REVIEW
         (not dropped); scores >= GROUNDING_NEAR_MISS_MIN are also logged for tuning.
    3. Canonicalizes field names against the 45-field ontology.
    4. Deduplicates by (field, operator, str(value)).
    """
    ALLOWED_OPERATORS = ALLOWED_OPERATORS
    OPERATOR_MAP = OPERATOR_MAP
    # thresholds live on the Settings page; the descriptor reads them at the moment of use
    GROUNDING_THRESHOLD = _SettingValue("GROUNDING_FUZZY_THRESHOLD")
    NEAR_MISS_MIN = _SettingValue("GROUNDING_NEAR_MISS_MIN")
    OCR_GROUNDING_THRESHOLD = _SettingValue("GROUNDING_OCR_THRESHOLD")


    @staticmethod
    def _number_not_in_quote(value: Any, quote: Any) -> bool:
        """True when `value` is a plain number (or 'N Crore/Lakh/years') that the quote never states."""
        if isinstance(value, bool) or value is None:
            return False
        m = re.fullmatch(r"\s*(?:rs\.?|inr|\u20b9)?\s*([\d,]+(?:\.\d+)?)\s*(?:crores?|cr|lakhs?|lacs?|years?|yrs?|days?|%)?\s*", str(value), re.I)
        if not m:
            return False
        digits = m.group(1).replace(",", "")
        text = str(quote or "").lower()
        flat = re.sub(r"(?<=\d)[,\s](?=\d)", "", text)               # '1,00,80,000' / '1 00 000' -> digits only
        numbers = {n.rstrip("0").rstrip(".") if "." in n else n for n in re.findall(r"\d+(?:\.\d+)?", flat)}
        if digits in numbers or digits.rstrip("0").rstrip(".") in numbers:
            return False
        try:
            as_int = int(float(digits))
        except ValueError:
            return False
        return not any(_WORDS.get(w) == as_int for w in re.findall(r"[a-z]+", text))

    _OR_GAP = re.compile(r"^\W*(?:or|and\s*/\s*or|either)\W*$", re.IGNORECASE)

    @classmethod
    def _group_alternatives(cls, criteria: List[CriterionSchema], chunk_text_map: Dict[str, str],
                            page_of: Optional[Dict[str, int]] = None) -> None:
        """Mark criteria of the same field whose quotes follow each other in the tender joined by 'or'."""
        page_of = page_of or {}
        located = []
        for k in criteria:
            quote = cls._normalize_text(k.source_text)
            if not quote:
                continue
            # the criterion's own chunk first, then any chunk of the same page (a page may be split in two chunks)
            candidates = [k.chunk_id] + [cid for cid, pg in page_of.items() if pg == k.page_no and cid != k.chunk_id]
            for cid in candidates:
                text = chunk_text_map.get(cid or "", "")
                at = text.find(quote) if text else -1
                if at >= 0:
                    located.append((cid, at, at + len(quote), k, text))
                    break
        located.sort(key=lambda t: (t[0] or "", t[1]))
        group = 0
        for (c1, s1, e1, k1, text), (c2, s2, e2, k2, _t) in zip(located, located[1:]):
            if c1 == c2 and k1.field == k2.field and k1.group == k2.group and s2 >= e1 and cls._OR_GAP.match(text[e1:s2]):
                if not k1.alt_group:
                    group += 1
                    k1.alt_group = f"ALT{group}"
                k2.alt_group = k1.alt_group

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """0-100 similarity of two whole quotes (not 'one inside the other')."""
        if not a or not b:
            return 0.0
        try:
            from rapidfuzz import fuzz
            return float(fuzz.ratio(a, b))
        except ImportError:
            from difflib import SequenceMatcher
            return 100.0 * SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _numbers_present(quote_norm: str, text_norm: str, ocr: bool = False) -> bool:
        """Every number in the quote must appear in the tender text it points to. Fuzzy matching alone accepts a
        quote with one digit changed ('6 years' for '5 years' still scores ~99), which would flip a verdict."""
        haystack = re.sub(r"[^a-z0-9]", "", text_norm)
        if ocr:                                    # scanned text: letters stand in for digits ('1O' for '10')
            haystack = haystack.translate(str.maketrans("oliszbg", "0115 289".replace(" ", "")[:7]))
        whole = set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d)", "", text_norm)))
        for token in re.findall(r"\d[\d,.\-/]*\d|\d", quote_norm):
            digits = re.sub(r"\D", "", token)
            if not digits:
                continue
            if digits not in haystack:
                return False
            if not ocr and not re.search(r"[\-/]|\d\.\d+\.\d", token) and token.replace(",", "") not in whole:     # dd.mm.yyyy is one token
                return False                       # '5' must not be accepted because the tender says '15'
        return True

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """
        NFKC normalization + whitespace collapse + dash/ligature folding.
        Used for both source_text and chunk_text before fuzzy comparison.
        """
        if not text:
            return ""
        # Unicode NFKC (folds ligatures, half-width chars, etc.)
        t = unicodedata.normalize("NFKC", text)
        t = t.lower()
        # Non-breaking space -> regular space
        t = t.replace("\u00a0", " ")
        # Smart quotes -> straight
        t = re.sub(r"[\u201c\u201d\u2018\u2019`]", "'", t)
        # En/em dash -> hyphen
        t = re.sub(r"[\u2013\u2014]", "-", t)
        # Soft hyphens (line-break artifacts from PyMuPDF)
        t = t.replace("\u00ad", "")
        # Collapse hyphen+whitespace (line-wrap artifacts e.g. "develop-\n ment")
        t = re.sub(r"-\s+", "", t)
        # Collapse whitespace
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @classmethod
    def validate_and_deduplicate(
        cls,
        criteria: List[CriterionSchema],
        chunks: List[ChunkSchema],
        run_id: str = None
    ) -> Tuple[List[CriterionSchema], Dict[str, Any]]:
        # Map chunk_id -> normalized chunk_text
        chunk_text_map: Dict[str, str] = {}
        ocr_chunk_ids = set()
        all_chunk_texts_norm: List[str] = []

        for c in chunks:
            norm_c = cls._normalize_text(c.chunk_text)
            chunk_text_map[c.chunk_id] = norm_c
            all_chunk_texts_norm.append(norm_c)
            if c.ocr_used:
                ocr_chunk_ids.add(c.chunk_id)

        ordered_ids = [c.chunk_id for c in sorted(chunks, key=lambda c: (c.physical_page, c.chunk_id))]
        validated_criteria: List[CriterionSchema] = []
        seen_keys: Dict[tuple, List[CriterionSchema]] = {}

        rejection_counts = {
            "SCHEMA_INVALID": 0,
            "GROUNDING_FAILED": 0,
            "DUPLICATE": 0,
            "INVALID_OPERATOR": 0,
            "MISSING_REQUIRED_FIELD": 0,
            "LLM_MALFORMED_OUTPUT": 0,
            "OTHER_VALIDATION_FAILURE": 0
        }

        for crit in criteria:
            # 1. Missing required field / null source_text validation
            src_str = str(crit.source_text).strip() if crit.source_text is not None else ""
            if not src_str or src_str.lower() in ("none", "null"):
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step(
                    "S7_POST_VALIDATOR",
                    page_no=crit.page_no,
                    criterion_id=crit.criterion_id,
                    status="REJECTED:NO_SOURCE_TEXT_PROVIDED",
                    message=f"Criterion {crit.criterion_id} ({crit.field}) discarded: it cites no text from the tender"
                )
                continue

            if not crit.field or not crit.field.strip():
                rejection_counts["MISSING_REQUIRED_FIELD"] += 1
                log_pipeline_step(
                    "S7_POST_VALIDATOR",
                    page_no=crit.page_no,
                    criterion_id=crit.criterion_id,
                    status="REJECTED:MISSING_REQUIRED_FIELD",
                    message=f"Criterion {crit.criterion_id} discarded: empty field"
                )
                continue

            # Noise filter: Discard Table of Contents dot leaders and pure document header lines
            src_str = str(crit.source_text or "").strip()
            if re.search(r"\.{4,}\s*\d+", src_str) or re.search(r"^Tender No\.?\s*:\s*[A-Z0-9_-]+$", src_str, re.IGNORECASE):
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step(
                    "S7_POST_VALIDATOR",
                    page_no=crit.page_no,
                    criterion_id=crit.criterion_id,
                    status="REJECTED:NOISE_HEADER",
                    message=f"Criterion {crit.criterion_id} discarded: Table of Contents or document header noise '{src_str}'"
                )
                continue

            # 2. Operator normalization & validation
            if crit.operator not in cls.ALLOWED_OPERATORS:
                op_clean = str(crit.operator).lower().strip()
                if op_clean in cls.OPERATOR_MAP:
                    crit.operator = cls.OPERATOR_MAP[op_clean]
                else:
                    rejection_counts["INVALID_OPERATOR"] += 1
                    log_pipeline_step(
                        "S7_POST_VALIDATOR",
                        page_no=crit.page_no,
                        criterion_id=crit.criterion_id,
                        status="REJECTED:INVALID_OPERATOR",
                        message=f"Criterion {crit.criterion_id} discarded: invalid operator '{crit.operator}'"
                    )
                    continue

            # 3. Schema field canonicalization via 45-field ontology
            crit.field = canonicalize_field(crit.field)

            # 3.0 A quote of blanks, dots or underscores (a signature line, a leader) states no requirement
            if len(re.findall(r"[^\W_]{2,}", src_str)) < 2:
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="REJECTED:EMPTY_QUOTE",
                                  message=f"{crit.criterion_id}: the quote '{src_str[:40]}' has no words; discarded")
                continue
            # 3a. The quote must speak about what the field says. A requirement filed under the wrong field would be
            #     judged against the wrong company record, so it is demoted to 'other' (manual review), never guessed.
            doubt = False                                # set when the quote only partly backs the criterion
            latin_quote = is_latin(crit.source_text)
            support = value_support(crit.value, crit.source_text) if latin_quote and is_latin(crit.value) else None
            if support == 0.0:                          # the quote never says what the criterion claims: invented
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="REJECTED:VALUE_NOT_IN_QUOTE",
                                  message=f"{crit.criterion_id}: value '{str(crit.value)[:60]}' is not in its quote; looks invented")
                continue
            gate = _field_gate(crit.field)
            excluded = _FIELD_EXCLUDE.get(crit.field)
            if excluded and latin_quote and excluded.search(str(crit.source_text)):
                # e.g. 'the EMD guarantee stays valid 90 days beyond the bid validity' states the EMD period, not the bid validity
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="REJECTED:FIELD_MISMATCH",
                                  message=f"{crit.criterion_id}: quote is about something else than '{crit.field}'")
                continue
            if gate and latin_quote and not gate.search(str(crit.source_text)):
                if crit.field in _NUMBER_NOISE_FIELDS or support is None and not isinstance(crit.value, (int, float)) and (
                        isinstance(crit.value, bool) or crit.value is None):
                    # procedural terms nobody checks, or a yes/no claim with no wording behind it: noise
                    rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                    log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                      status="REJECTED:FIELD_MISMATCH",
                                      message=f"{crit.criterion_id}: quote does not mention '{crit.field}'")
                    continue
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="RE_CANONICALIZED",
                                  message=f"{crit.criterion_id}: quote does not mention '{crit.field}'; moved to 'other' for manual review")
                crit.field = "other"
            if isinstance(crit.value, (list, tuple)) and len(crit.value) > 1 and support is not None and support < 1.0:
                kept_items = [v for v in crit.value if value_support([v], crit.source_text) == 1.0]
                if kept_items and len(kept_items) < len(crit.value):
                    log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                      status="REPAIRED:VALUE_TRIMMED",
                                      message=f"{crit.criterion_id}: dropped {[v for v in crit.value if v not in kept_items]} (not in the quote)")
                    crit.value = kept_items
                    support = 1.0
            if support is not None and support < 1.0:
                doubt = True                            # part of the value is not in the quote: a person must check
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="NEEDS_REVIEW:VALUE_PARTLY_IN_QUOTE",
                                  message=f"{crit.criterion_id}: only part of '{str(crit.value)[:60]}' is in its quote")
            if crit.field == "blacklisted" and str(crit.value).strip().lower() in ("no", "false", "not blacklisted", "none", "nil", "0", ""):
                crit.value = False                      # one meaning, however the model spelled it

            # 3b. Value Type Safety Guard: Prevent dates, times, SLAs, validity windows, and URLs from occupying numeric capacity fields
            NUMERIC_CAPACITY_FIELDS = {
                "project_value", "annual_turnover", "net_worth", "experience_years",
                "years_in_business", "employee_count", "bid_validity_days"
            }
            val_str = str(crit.value or "").strip()
            src_str_l = str(crit.source_text or "").lower()
            if crit.field in NUMERIC_CAPACITY_FIELDS and crit.field != "bid_validity_days":
                has_unit = bool(re.search(r"crores?|\bcr\b|lakhs?|lacs?|\brs\b|inr|\u20b9|years?|\bmillion", val_str + " " + src_str_l[:0], re.IGNORECASE))
                is_date_time_url_or_procedural = (
                    re.search(r"\b\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4}\b|\b20\d{2}[\./\-]\d{1,2}[\./\-]\d{1,2}\b", val_str) or
                    re.search(r"\b\d{1,2}:\d{2}\b|\b\d{1,2}[:\.]\d{2}\s*(?:AM|PM|Hours|hrs)\b", val_str, re.IGNORECASE) or
                    re.search(r"https?://|www\.|\.gov\.in|\.com", val_str, re.IGNORECASE) or
                    any(re.search(rf"\b{t}\b", val_str.lower()) for t in ["hours", "due date", "deadline", "submission", "days", "weeks", "notice", "schedule", "milestone", "sla", "score", "marks", "weightage", "seconds"]) or
                    (not has_unit and any(t in src_str_l for t in ["bid validity", "valid for", "bid security", "earnest money", "notice period", "score of", "maximum score", "marks per"]))
                )
                if is_date_time_url_or_procedural:
                    if "http" in val_str.lower() or "www." in val_str.lower() or ".gov.in" in val_str.lower():
                        crit.field = "submission_portal"
                    elif any(k in val_str.lower() or k in src_str_l for k in ["deadline", "due date", "submission", "time"]):
                        crit.field = "submission_deadline"
                    else:
                        crit.field = "other"
                    log_pipeline_step(
                        "S7_POST_VALIDATOR",
                        page_no=crit.page_no,
                        criterion_id=crit.criterion_id,
                        status="RE_CANONICALIZED",
                        message=f"Re-canonicalized {crit.criterion_id} from numeric capacity field to '{crit.field}' (value='{val_str}')"
                    )

            # 3b2. Procedural fields carry a number / date / URL; a sentence there ('as explained below') is noise
            if crit.field in _NUMBER_NOISE_FIELDS and (isinstance(crit.value, bool) or not isinstance(crit.value, (int, float))) and not re.search(
                    r"\d|https?://|www\.|\.gov\.in|\.com", str(crit.value)):
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="REJECTED:NO_VALUE",
                                  message=f"Criterion {crit.criterion_id} ({crit.field}) discarded: value '{str(crit.value)[:60]}' has no number, date or URL")
                continue

            # 3c. A number the model reports must be stated in the quote it cites (a page number or an invented
            #     figure is not a requirement). Informational fields are dropped; capacity fields go to review.
            if cls._number_not_in_quote(crit.value, crit.source_text):
                if crit.field in _NUMBER_NOISE_FIELDS:
                    rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                    log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                      status="REJECTED:VALUE_NOT_IN_QUOTE",
                                      message=f"Criterion {crit.criterion_id} discarded: value '{crit.value}' is not in its quote")
                    continue
                if not re.search(r"\d", str(crit.source_text)) and not any(w in _WORDS for w in re.findall(r"[a-z]+", str(crit.source_text).lower())):
                    rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                    log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                      status="REJECTED:VALUE_NOT_IN_QUOTE",
                                      message=f"{crit.criterion_id}: quote has no number but the value is '{crit.value}'; invented")
                    continue
                doubt = True
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="NEEDS_REVIEW:VALUE_NOT_IN_QUOTE",
                                  message=f"Criterion {crit.criterion_id} ({crit.field}): value '{crit.value}' not found in its quote")

            if crit.field == "other" and is_latin(src_str) and (
                    isinstance(crit.value, bool) or not _REQUIREMENT_CUE.search(src_str)):
                # an unclassified item must at least read like a requirement; a note or a yes/no with no wording is noise
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="REJECTED:NOT_A_REQUIREMENT",
                                  message=f"{crit.criterion_id}: '{src_str[:60]}' does not read like a bidder requirement; discarded")
                continue

            # 4. Fuzzy Grounding Verification (NFKC + rapidfuzz partial_ratio)

            src_norm = cls._normalize_text(crit.source_text)[:_MAX_FUZZY_QUOTE]      # a runaway quote must not turn into minutes of matching
            verified = False
            best_ratio = 0.0
            best_span: Optional[List[int]] = None

            def _find_span(haystack: str, needle: str) -> Optional[List[int]]:
                """Return [start, end] char span if needle fuzzy-matches anywhere in haystack."""
                ratio = _partial_ratio(needle, haystack)
                if ratio >= cls.GROUNDING_THRESHOLD:
                    # Approximate span: locate best matching window
                    try:
                        idx = haystack.find(needle[:30])  # anchor on first 30 chars
                        if idx >= 0:
                            return [idx, idx + len(needle)]
                    except Exception:
                        pass
                    return [0, len(needle)]  # fallback span
                return None

            # Relaxed threshold only for OCR chunks (OCR noise); native text uses the strict one
            is_ocr_chunk = bool(crit.chunk_id and crit.chunk_id in ocr_chunk_ids)
            effective_threshold = cls.OCR_GROUNDING_THRESHOLD if is_ocr_chunk else cls.GROUNDING_THRESHOLD

            # Check assigned chunk first
            if crit.chunk_id and crit.chunk_id in chunk_text_map:
                chunk_norm = chunk_text_map[crit.chunk_id]
                ratio = _partial_ratio(src_norm, chunk_norm)
                if ratio >= effective_threshold and cls._numbers_present(src_norm, chunk_norm, is_ocr_chunk):
                    verified = True
                    best_ratio = ratio
                    best_span = _find_span(chunk_norm, src_norm)
                elif ratio >= cls.NEAR_MISS_MIN:
                    best_ratio = ratio

            # Fall back to all chunks
            if not verified:
                for other_id, chunk_norm in chunk_text_map.items():
                    ratio = _partial_ratio(src_norm, chunk_norm)
                    if ratio >= cls.GROUNDING_THRESHOLD and cls._numbers_present(src_norm, chunk_norm, other_id in ocr_chunk_ids):
                        verified = True
                        best_ratio = ratio
                        best_span = _find_span(chunk_norm, src_norm)
                        if other_id != crit.chunk_id:             # the quote lives elsewhere: cite the right page
                            home = next((c for c in chunks if c.chunk_id == other_id), None)
                            if home is not None:
                                crit.chunk_id, crit.page_no = home.chunk_id, home.physical_page
                        break
                    if ratio > best_ratio:
                        best_ratio = ratio

            if not verified and len(ordered_ids) > 1:
                # a clause that runs over a page break is split between two chunks: look for the quote across the join
                for first, second in zip(ordered_ids, ordered_ids[1:]):
                    joined = chunk_text_map[first] + " " + chunk_text_map[second]
                    ratio = _partial_ratio(src_norm, joined)
                    if ratio >= cls.GROUNDING_THRESHOLD and cls._numbers_present(src_norm, joined, first in ocr_chunk_ids):
                        verified, best_ratio = True, ratio
                        home = next((c for c in chunks if c.chunk_id == first), None)
                        if home is not None and crit.chunk_id not in (first, second):
                            crit.chunk_id, crit.page_no = home.chunk_id, home.physical_page
                        break

            floor = (cls.OCR_GROUNDING_THRESHOLD if is_ocr_chunk else cls.NEAR_MISS_MIN) - 10
            if not verified and best_ratio < floor:
                # the quote is not in the tender at all (a model that repeats my own examples back): drop it
                rejection_counts["NOISE_REJECTED"] = rejection_counts.get("NOISE_REJECTED", 0) + 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=crit.page_no, criterion_id=crit.criterion_id,
                                  status="REJECTED:QUOTE_NOT_IN_TENDER",
                                  message=f"{crit.criterion_id} ({crit.field}): quote not found in the tender (best match {best_ratio:.0f}%); discarded")
                continue

            if not verified:
                if best_ratio >= cls.NEAR_MISS_MIN:
                    # Near-miss: log for threshold tuning
                    near_miss_entry = {
                        "criterion_id": crit.criterion_id,
                        "field": crit.field,
                        "source_text": crit.source_text[:100],
                        "best_ratio": round(best_ratio, 1),
                        "threshold": cls.GROUNDING_THRESHOLD,
                    }
                    _near_miss_log.append(near_miss_entry)
                    near_miss_logger.info("NEAR_MISS %s", near_miss_entry)

                rejection_counts["GROUNDING_FAILED"] += 1
                crit.exact_match = False
                log_pipeline_step(
                    "S7_POST_VALIDATOR",
                    page_no=crit.page_no,
                    criterion_id=crit.criterion_id,
                    status="NEEDS_REVIEW:GROUNDING_UNVERIFIED",
                    message=(
                        f"Criterion {crit.criterion_id} ({crit.field}) routed to NEEDS_REVIEW: "
                        f"grounding unverified (best_ratio={best_ratio:.1f} < threshold={cls.GROUNDING_THRESHOLD})."
                    )
                )
            else:
                crit.exact_match = not doubt
                try:
                    if best_span:
                        object.__setattr__(crit, "source_span", best_span)
                except Exception:
                    pass

            # 5. Deduplication: same (field, operator, value) is one requirement, unless both copies are verified
            #    and quote different text (e.g. two table rows that each ask for 5 years of something)
            base_key = (crit.field.lower(), crit.operator, str(crit.value).lower().strip(), (crit.group or "").split(" — ")[0])
            def _same_requirement(k: CriterionSchema) -> bool:
                if cls._text_similarity(src_norm, cls._normalize_text(k.source_text)) >= 88:
                    return True                       # the same clause printed again (body and annexure format)
                if crit.field != "other" and not re.search(r"\d", str(crit.value)):
                    return True                       # the same non-numeric requirement repeated on other pages
                if crit.field in ("blacklisted", "insolvency_status", "letter_of_authorization", "company_website"):
                    return True                       # one fact however many clauses repeat it
                if crit.field in _SINGLE_THRESHOLD_FIELDS:
                    return True                       # the same threshold printed in the body, a form and an annexure
                if cls._normalize_text(k.source_text)[:160] == src_norm[:160]:
                    return True
                if crit.operator == "SUBMITTED" and crit.field != "other":
                    return True                       # the same document asked for on two pages is one thing to prepare
                if k.exact_match and crit.exact_match:
                    return False                      # two verified, different quotes: two requirements
                # an unverified copy is the same requirement only when it sits on the same page or reads alike
                return k.page_no == crit.page_no or _partial_ratio(src_norm[:200], cls._normalize_text(k.source_text)) >= 80
            twin = next((k for k in seen_keys.get(base_key, []) if _same_requirement(k)), None)
            if twin is not None:
                if crit.exact_match and not twin.exact_match:
                    # the later copy has a verified quote; keep it instead of the unverified first one
                    validated_criteria[validated_criteria.index(twin)] = crit
                    seen_keys[base_key][seen_keys[base_key].index(twin)] = crit
                rejection_counts["DUPLICATE"] += 1
                log_pipeline_step(
                    "S7_POST_VALIDATOR",
                    page_no=crit.page_no,
                    criterion_id=crit.criterion_id,
                    status="REJECTED:DUPLICATE",
                    message=f"Criterion {crit.criterion_id} ({crit.field}) discarded: duplicate criterion"
                )
                continue

            seen_keys.setdefault(base_key, []).append(crit)
            validated_criteria.append(crit)

        # 5a. an unverified copy of a clause that another criterion quotes correctly (same field, other number) is a
        #     misreading of that clause: keep the verified one only
        verified_rows = [k for k in validated_criteria if k.exact_match]
        for k in list(validated_criteria):
            if k.exact_match:
                continue
            kq = cls._normalize_text(k.source_text)
            if any(v.field == k.field and cls._text_similarity(kq, cls._normalize_text(v.source_text)) >= 80 for v in verified_rows):
                validated_criteria.remove(k)
                rejection_counts["DUPLICATE"] += 1
                log_pipeline_step("S7_POST_VALIDATOR", page_no=k.page_no, criterion_id=k.criterion_id,
                                  status="REJECTED:DUPLICATE", message=f"{k.criterion_id}: misreads a clause already captured; discarded")

        # 5b. 'One work of X, Two works of Y, Three works of Z' is one requirement; its count half only repeats it
        by_quote: Dict[str, List[CriterionSchema]] = {}
        for k in validated_criteria:
            by_quote.setdefault(cls._normalize_text(k.source_text)[:140], []).append(k)
        for group in by_quote.values():
            if any(k.field == "similar_work_value" for k in group):
                for k in group:
                    if k.field == "contract_count":
                        validated_criteria.remove(k)
                        rejection_counts["DUPLICATE"] += 1

        # 5b2. a relaxation for start-ups / MSEs is an alternative to the main threshold, not a second must-have
        for k in validated_criteria:
            if k.field in _SINGLE_THRESHOLD_FIELDS and _RELAXATION.search(k.source_text or "") and k.mandatory:
                if any(o is not k and o.field == k.field and str(o.value) != str(k.value) for o in validated_criteria):
                    k.mandatory = False

        # 5c. 'One work of X, or Two works of Y, or Three works of Z': alternatives, meeting one is enough
        cls._group_alternatives(validated_criteria, chunk_text_map, {c.chunk_id: c.physical_page for c in chunks})

        # 6. Handle 0 criteria gracefully without crashing pipeline
        if not validated_criteria:
            log_pipeline_step(
                "S7_POST_VALIDATOR",
                status="WARNING",
                message="0 valid criteria remaining after post-validation. Proceeding to report builder."
            )

        schema_rejected = (
            rejection_counts["SCHEMA_INVALID"] +
            rejection_counts["INVALID_OPERATOR"] +
            rejection_counts["MISSING_REQUIRED_FIELD"] +
            rejection_counts["LLM_MALFORMED_OUTPUT"] +
            rejection_counts["OTHER_VALIDATION_FAILURE"]
        )
        grounding_failures = rejection_counts["GROUNDING_FAILED"]
        duplicates_removed = rejection_counts["DUPLICATE"]
        noise_rejected = rejection_counts.get("NOISE_REJECTED", 0)
        total_rejected = schema_rejected + noise_rejected + duplicates_removed

        metrics = {
            "raw_criteria_found": len(criteria),
            "schema_rejected": schema_rejected,
            "grounding_failures": grounding_failures,
            "duplicates_removed": duplicates_removed,
            "criteria_grounded": len(validated_criteria),
            "criteria_rejected": total_rejected,
            "noise_rejected": noise_rejected,
            "ungrounded_kept_for_review": sum(1 for c in validated_criteria if not c.exact_match),
            "rejection_reasons_breakdown": rejection_counts
        }

        log_pipeline_step(
            "S7_POST_VALIDATOR",
            status="SUCCESS",
            message=f"Validated {len(validated_criteria)} grounded criteria (Raw: {len(criteria)}, Rejected: {total_rejected} [Schema: {schema_rejected}, Noise: {noise_rejected}, Duplicates: {duplicates_removed}]; unverified quotes kept for review: {grounding_failures})"
        )
        return validated_criteria, metrics

