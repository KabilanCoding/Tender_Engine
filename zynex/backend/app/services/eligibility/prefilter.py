"""Deterministic pre-filter: decide which chunks of a LARGE tender are worth an LLM call.

A big tender is mostly boilerplate (scope, legal terms, forms) and eligibility requirements sit in a few
sections, so asking the model about every page wastes most of the run time. Chunks are scored on
eligibility vocabulary; only the best-scoring share is sent to the model, plus the neighbours of the
very strongest pages (requirements often continue across a page break).

Nothing is dropped silently: skipped chunks are counted in the run metrics. Small documents are never
filtered, and the filter can be switched off with ELIGIBILITY_PREFILTER=false.
"""
import math
import re
from typing import Dict, List, Set, Tuple

from app.schemas.eligibility import ChunkSchema
from app.services.eligibility.multilingual import ELIGIBILITY_TERMS, count_terms

# (pattern, weight): weight 2 = discriminates eligibility text from boilerplate, 1 = supporting vocabulary
_SIGNALS = [(re.compile(p, re.IGNORECASE), w) for p, w in (
    (r"eligib", 2), (r"qualif", 2), (r"turnover", 2), (r"net\s*worth", 2), (r"solvency", 2),
    (r"blacklist|black\s+listed|debar", 2), (r"similar\s+(?:work|project|nature)", 2),
    (r"work\s+orders?", 2), (r"completion\s+certificate|performance\s+certificate", 2),
    (r"\bbidder\b.{0,40}\b(?:must|shall|should)\b", 2),
    (r"\b(?:must|shall)\s+(?:have|possess|submit|furnish|produce|be\s+registered)\b", 2),
    (r"minimum\s+(?:of\s+)?(?:\d|rs|inr|₹)", 2), (r"audited\s+(?:balance|financial)", 2),
    (r"\biso\b", 1), (r"cmmi", 1), (r"stqc", 1), (r"\bgst\b", 1), (r"\bpan\b", 1), (r"\bmsme\b|udyam", 1),
    (r"\bemd\b|earnest\s+money|bid\s+security|tender\s+fee", 1), (r"bid\s+validity", 1),
    (r"consortium|joint\s+venture", 1), (r"experience", 1), (r"certif", 1), (r"working\s+capital", 1),
    (r"at\s+least\s+(?:\d|rs|inr|one|two|three)", 1), (r"key\s+(?:personnel|professional)", 1),
    (r"annexure|undertaking|declaration|affidavit|power\s+of\s+attorney", 1),
)]
_HEADING = re.compile(r"eligib|qualif|criteria|requirement|submission|documents?\s+required|checklist|"
                      r"instructions?\s+to\s+bidders|disqualif", re.IGNORECASE)

MIN_SCORE = 3           # below this a chunk is never sent
STRONG_SCORE = 6        # chunks at least this strong also pull in their neighbours


_SCORING = re.compile(r"\bmarks?\b|\bscor(?:e|es|ing)\b|weightage|\bpoints\b|\bmaximum\s+score", re.IGNORECASE)


def score_chunk(chunk: ChunkSchema) -> int:
    score = sum(weight for pattern, weight in _SIGNALS if pattern.search(chunk.chunk_text))
    score += min(6, 2 * count_terms(chunk.chunk_text, ELIGIBILITY_TERMS))     # the same signals in other languages
    n_scoring = len(_SCORING.findall(chunk.chunk_text))
    if n_scoring >= 8:
        score = 0                         # a page that is mostly marks and scores is an evaluation table
    elif n_scoring >= 4:
        score = max(0, score - 5)         # an evaluation / marks table talks about turnover and experience, but awards points
    if _HEADING.search(f"{chunk.chapter or ''} {chunk.section or ''}"):
        score += 2
    if chunk.content_type == "table" and score:
        score += 1
    return score


def select_chunks(chunks: List[ChunkSchema], max_fraction: float = 0.4, min_keep: int = 12,
                  neighbours: int = 1) -> Tuple[Set[str], Dict[str, int]]:
    """Return (chunk ids to send to the model, score per chunk id). Never returns an empty selection."""
    scores = {c.chunk_id: score_chunk(c) for c in chunks}
    ranked = sorted((c for c in chunks if scores[c.chunk_id] >= MIN_SCORE),
                    key=lambda c: (-scores[c.chunk_id], c.physical_page))
    budget = max(min_keep, math.ceil(max_fraction * len(chunks)))
    keep: Set[str] = {c.chunk_id for c in ranked[:budget]}

    index = {c.chunk_id: i for i, c in enumerate(chunks)}
    for cid in list(keep):
        if scores[cid] >= STRONG_SCORE:
            i = index[cid]
            keep.update(chunks[j].chunk_id for j in range(max(0, i - neighbours), min(len(chunks), i + neighbours + 1)))
    return (keep or {c.chunk_id for c in chunks}), scores
