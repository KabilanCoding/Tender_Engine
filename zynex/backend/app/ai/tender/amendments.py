"""Corrigendum step: list what an amendment document changes (item, old wording, new wording).

One short AI call over the whole (few-page) corrigendum. Every change the model reports is kept only if its NEW wording
really appears in the document, so an invented change cannot reach the report.
"""
import re
from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

from app.ai.tender import llm_call
from app.ai.tender.json_parse import parse_json_robust
from app.ai.tender.run_options import RunOptions
from app.services.eligibility.pipeline_log import log_pipeline_step

SYSTEM_PROMPT = (
    "You read a corrigendum: a notice that changes parts of a tender. List every change it makes. "
    "For each change give: item (what is changed, e.g. 'Last date of submission'), old (the old wording or value, "
    "empty if not shown) and new (the new wording or value, copied exactly from the document). "
    "Use only words that are in the document. Do not invent or explain. Return JSON only.")

SCHEMA = {"type": "object", "properties": {"changes": {"type": "array", "items": {
    "type": "object", "properties": {"item": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
    "required": ["item", "new"]}}}, "required": ["changes"]}


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", str(text or "").lower()).strip()


def verify(changes: List[Dict[str, Any]], text: str) -> List[Dict[str, str]]:
    """Keep a change only when its new wording is in the document (fuzzy, to survive OCR noise)."""
    haystack = _norm(text)
    kept: List[Dict[str, str]] = []
    for ch in changes or []:
        item, new, old = str(ch.get("item") or "").strip(), str(ch.get("new") or "").strip(), str(ch.get("old") or "").strip()
        if not item or len(_norm(new)) < 3:
            continue
        if _norm(new) in haystack or fuzz.partial_ratio(_norm(new), haystack) >= 90:
            if (item, new) not in {(k["item"], k["new"]) for k in kept}:
                kept.append({"item": item[:160], "old": old[:300], "new": new[:400]})
    return kept


async def extract_amendments(text: str, options: Optional[RunOptions] = None) -> List[Dict[str, str]]:
    body = (text or "").strip()[:12000]
    if not body:
        return []
    for attempt in range(2):
        try:
            content = await llm_call.chat_json(SYSTEM_PROMPT, f"Corrigendum text:\n{body}", SCHEMA, attempt=attempt,
                                               temperature=0.0, options=options)
            parsed = parse_json_robust(content, required_key="changes")
            rows = parsed.get("changes") if isinstance(parsed, dict) else parsed
            return verify(rows if isinstance(rows, list) else [], body)
        except Exception as e:
            log_pipeline_step("S10_AMENDMENTS", status="WARNING", message=f"attempt {attempt + 1} failed: {type(e).__name__}: {e}")
    return []


def describe(changes: List[Dict[str, str]]) -> str:
    """Plain sentence list for the report summary."""
    parts = []
    for c in changes[:8]:
        parts.append(f"{c['item']}: " + (f"{c['old']} → " if c.get("old") else "now ") + c["new"])
    return " Changes made by this corrigendum: " + "; ".join(parts) + "." if parts else ""
