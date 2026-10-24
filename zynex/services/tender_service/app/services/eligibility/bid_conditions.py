"""Bid conditions found by plain text search (no AI): EMD and tender fee, consortium, sub-contracting, source code.

The AI looks for eligibility rules; these conditions sit elsewhere in a tender and were being missed. Each hit is a
sentence copied word for word from the tender with its page, so it is grounded by construction. They are reported as
'for information' / 'check by hand', never as pass or fail, and never block the verdict.
"""
import re
from typing import List, Optional, Tuple

from app.schemas.eligibility import ChunkSchema, CriterionSchema
from app.services.eligibility.normalizer import Normalizer

_AMOUNT = r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?)?"
_MONEY_RULES = [
    ("emd_amount", re.compile(r"(?:\bemd\b|earnest\s+money(?:\s+deposit)?|bid\s+security)[^.]{0,90}?" + _AMOUNT, re.I)),
    ("tender_fee", re.compile(r"(?:tender|bid|document|rfp)\s+(?:document\s+)?fees?[^.]{0,60}?" + _AMOUNT, re.I)),
]
# (key, pattern, shown as)
_TEXT_RULES: List[Tuple[str, "re.Pattern[str]", str]] = [
    ("consortium", re.compile(r"no\s+consortium|consortium[^.]{0,40}\bnot\s+(?:be\s+)?(?:allowed|permitted)|shall\s+not\s+form\s+any\s+consortium", re.I),
     "Consortium is not allowed"),
    ("consortium", re.compile(r"consortium[^.]{0,60}\b(?:allowed|permitted|may\s+(?:bid|participate))", re.I), "Consortium is allowed"),
    ("subcontract", re.compile(r"sub[\s-]?(?:letting|contracting)[^.]{0,60}\bnot\s+(?:be\s+)?allowed|shall\s+not\s+sub[\s-]?contract", re.I),
     "Sub-contracting is not allowed"),
    ("source_code", re.compile(r"source\s+code[^.]{0,120}(?:hand(?:ed)?\s*over|submit|deliver|property|ownership|vest|escrow)|"
                               r"(?:hand(?:ed)?\s*over|submit|deliver)[^.]{0,60}source\s+code", re.I), "Source code must be handed over"),
]


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return re.sub(r"\s+", " ", text[left:right]).strip()[:300]


# ── the same term stated with different numbers in one tender ────────────────────────────────────────────────────
_NOT_THE_BID = re.compile(r"\bemd\b|\bbg\b|bank\s+guarantee|earnest|warranty|\bamc\b|support\s+period", re.I)
_CONFLICT_RULES = [
    # (label, pattern with one numeric group, unit, skip sentences that talk about something else)
    ("Bid validity", re.compile(r"(?:bid|offer|proposal|tender|quotation)s?\b[^.]{0,40}?valid(?:ity)?[^.]{0,60}?(\d{2,3})\s*(?:\([a-z\s-]{0,60}\)\s*)?days|"
                                r"validity\s+(?:period\s+)?(?:of\s+)?(?:the\s+)?(?:bid|offer|proposal|tender)[^.]{0,40}?(\d{2,3})\s*(?:\([a-z\s-]{0,60}\)\s*)?days", re.I), "days", True),
    ("Performance guarantee", re.compile(r"performance\s+(?:bank\s+)?(?:guarantee|security)[^.]{0,120}?(\d{1,2}(?:\.\d+)?)\s*%|"
                                         r"(\d{1,2}(?:\.\d+)?)\s*%\s*of\s+(?:the\s+)?(?:contract|order|project|total)\s+(?:value|cost|price)[^.]{0,80}?performance\s+(?:bank\s+)?(?:guarantee|security)|"
                                         r"\bguarantee\b[^%]{0,80}?(\d{1,2}(?:\.\d+)?)\s*%\s*of\s+(?:the\s+)?(?:contract|order|project)\s+value", re.I), "%", False),
    ("Security deposit", re.compile(r"security\s+deposit[^.]{0,100}?(\d{1,2}(?:\.\d+)?)\s*%", re.I), "%", False),
    ("Liquidated damages cap", re.compile(r"liquidated\s+damages[^.]{0,160}?(?:maximum|max\.?|capped|ceiling|not\s+(?:to\s+)?exceed)[^.]{0,40}?(\d{1,2}(?:\.\d+)?)\s*%", re.I), "%", False),
]


def find_conflicts(chunks: List[ChunkSchema]) -> List[CriterionSchema]:
    """One row per term that the tender states with different numbers in different places (a copy-paste or amendment slip).
    Each is reported for a person to resolve; nothing is decided here."""
    out: List[CriterionSchema] = []
    for label, rx, unit, skip_other in _CONFLICT_RULES:
        seen = {}                                  # number -> (page, sentence, chunk)
        for chunk in sorted(chunks, key=lambda c: c.physical_page):
            text = re.sub(r"\s+", " ", chunk.chunk_text)            # a sentence often wraps over lines
            for m in rx.finditer(text):
                num = next((g for g in m.groups() if g), None)
                if num is None:
                    continue
                sentence = _sentence(text, m.start(), m.end())
                if skip_other and _NOT_THE_BID.search(sentence):
                    continue
                if label == "Performance guarantee" and not re.search(r"performance|\bpbg\b", text[max(0, m.start() - 160):m.end()], re.I):
                    continue                              # a bank guarantee of another kind
                key = f"{float(num):g}"
                seen.setdefault(key, (chunk.physical_page, sentence, chunk))
        if len(seen) > 1:
            first = min(seen.values(), key=lambda v: v[0])
            shown = ", ".join(f"{k}{' ' + unit if unit == 'days' else unit} (page {v[0]})" for k, v in sorted(seen.items(), key=lambda kv: kv[1][0]))
            out.append(CriterionSchema(criterion_id="X%03d" % (len(out) + 1), chunk_id=first[2].chunk_id, page_no=first[0],
                                       section=first[2].section, field="other", operator="contains",
                                       value=f"{label} is stated differently in this tender: {shown}. Ask the buyer which applies.",
                                       mandatory=False, source_text=first[1], exact_match=True))
    return out


def find_bid_conditions(chunks: List[ChunkSchema], existing: List[CriterionSchema]) -> List[CriterionSchema]:
    have = {c.field for c in existing}
    found: List[CriterionSchema] = []
    seen = set()

    def add(field: str, op: str, value, chunk: ChunkSchema, quote: str, key: Optional[str] = None) -> None:
        k = key or field
        if k in seen:
            return
        seen.add(k)
        found.append(CriterionSchema(criterion_id="B%03d" % (len(found) + 1), chunk_id=chunk.chunk_id, page_no=chunk.physical_page,
                                     section=chunk.section, field=field, operator=op, value=value, mandatory=False,
                                     source_text=quote, exact_match=True))
    for chunk in sorted(chunks, key=lambda c: c.physical_page):
        text = chunk.chunk_text
        for field, rx in _MONEY_RULES:
            if field in have:
                continue
            m = rx.search(text)
            if m:
                amount = Normalizer.parse_numeric(f"{m.group(1)} {m.group(2) or ''}")
                if amount:
                    add(field, "==", amount, chunk, _sentence(text, m.start(), m.end()))
        for key, rx, _label in _TEXT_RULES:
            if key in seen:
                continue
            m = rx.search(text)
            if m:
                add("other", "contains", _label, chunk, _sentence(text, m.start(), m.end()), key=key)
    return found + find_conflicts(chunks)
