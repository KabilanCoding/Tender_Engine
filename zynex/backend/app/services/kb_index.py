"""Searchable index of the company knowledge base (RAG, used only to FIND rows).

What it does          : one short text per project / employee / certificate / client / technology, embedded locally with
                        the model chosen on the Settings page (default bge-m3), so "railway work" also finds "transit" and "metro" projects.
What it never does    : decide anything numeric. Values, dates, counts and registration numbers are read from the tables by
                        code. The search only says WHICH rows look relevant; the rule engine then checks their numbers.
What is never indexed : bank account, IFSC, e-mail addresses, GST/PAN numbers (rows of company_profile are not indexed at all).
Row = passage         : each text is 20-120 words, so there is nothing to split into chunks.
"""
import hashlib
import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm_client import llm_client
from app.models.knowledge_base import Certification, Client, Employee, KbPassage, Project, Technology

_WORD = re.compile(r"[a-z0-9\+#\.]{2,}")


def _clean(*parts: Any) -> str:
    return re.sub(r"\s+", " ", " | ".join(str(p).strip() for p in parts if p not in (None, "", [], "None"))).strip()


async def build_passages(db: AsyncSession) -> List[Tuple[str, int, str]]:
    """[(table, row id, text)] for every row worth finding by meaning."""
    clients = {c.id: c for c in (await db.execute(select(Client))).scalars()}
    out: List[Tuple[str, int, str]] = []
    for p in (await db.execute(select(Project))).scalars():
        cl = clients.get(p.client_id)
        out.append(("projects", p.id, _clean(
            f"Project: {p.name}", f"Client: {cl.name} ({cl.client_type or cl.industry or ''})" if cl else None,
            f"Domain: {p.domain}" if p.domain else None, f"Status: {p.status}" if p.status else None,
            f"Technologies: {', '.join(p.technologies or [])}" if p.technologies else None, p.description)))
    for e in (await db.execute(select(Employee).where(Employee.is_active.is_(True)))).scalars():
        out.append(("employees", e.id, _clean(
            f"Role: {e.role}", f"Department: {e.department}" if e.department else None,
            f"Qualification: {e.qualification}" if e.qualification else None,
            f"Certifications: {e.professional_certifications}" if e.professional_certifications else None,
            f"Skills: {', '.join(e.skills or [])}" if e.skills else None,
            f"Experience: {e.experience_years:g} years" if e.experience_years else None)))
    for c in (await db.execute(select(Certification))).scalars():
        out.append(("certifications", c.id, _clean(f"Certificate: {c.name}", f"Issued by: {c.issuing_body}" if c.issuing_body else None)))
    for c in clients.values():
        out.append(("clients", c.id, _clean(f"Client: {c.name}", c.client_type or c.industry, c.state_region)))
    for t in (await db.execute(select(Technology))).scalars():
        out.append(("technologies", t.id, _clean(f"Technology: {t.name}", t.category, t.proficiency)))
    return out


def _model() -> str:
    from app.core.config import settings
    return settings.EMBED_MODEL or "bge-m3"


def _hash(text: str) -> str:
    """Includes the embedding model: after the model is changed every row counts as out of date and is embedded again."""
    return hashlib.sha1(f"{_model()}|{text}".encode()).hexdigest()


async def rebuild(db: AsyncSession) -> Dict[str, int]:
    """Bring the index in line with the tables: embed new/changed rows, drop rows that no longer exist."""
    wanted = await build_passages(db)
    have = {(p.source_table, p.source_id): p for p in (await db.execute(select(KbPassage))).scalars()}
    added = updated = failed = 0
    for table, rid, text in wanted:
        row, digest = have.pop((table, rid), None), _hash(text)
        if row is not None and row.content_hash == digest and row.embedding:
            continue
        try:
            vector = await llm_client.embed(text)
        except Exception:
            vector, failed = None, failed + 1
        if row is None:
            db.add(KbPassage(source_table=table, source_id=rid, text=text, content_hash=digest, embedding=vector, embed_model=_model()))
            added += 1
        else:
            row.text, row.content_hash, row.embedding, row.embed_model = text, digest, vector, _model()
            updated += 1
    for gone in have.values():                       # the row was deleted from its table
        await db.delete(gone)
    await db.commit()
    return {"added": added, "updated": updated, "removed": len(have), "failed_to_embed": failed, "total": len(wanted)}


async def status(db: AsyncSession) -> Dict[str, Any]:
    rows = list((await db.execute(select(KbPassage))).scalars())
    wanted = await build_passages(db)
    by_key = {(p.source_table, p.source_id): p for p in rows}
    stale = sum(1 for t, i, text in wanted if (t, i) not in by_key or by_key[(t, i)].content_hash != _hash(text))
    return {"indexed": sum(1 for p in rows if p.embedding), "rows_in_tables": len(wanted), "out_of_date": stale,
            "ready": bool(rows) and stale == 0}


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


_STOP = {"the", "and", "for", "with", "that", "this", "have", "has", "shall", "should", "must", "bidder", "bidders", "applicant",
         "firm", "company", "agency", "least", "minimum", "years", "year", "value", "not", "any", "all", "from", "such", "which",
         "work", "works", "project", "projects", "experience", "similar", "nature", "executed", "completed", "implementation",
         "during", "last", "past", "preceding", "than", "more", "less", "each", "one", "two", "three", "per", "its", "are", "was",
         "were", "been", "being", "other", "also", "into", "over", "under", "above", "below", "total", "cost", "rs", "inr", "crore",
         "crores", "lakh", "lakhs", "government", "department", "organization", "organisation", "psu", "central", "state", "india"}


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD.findall(str(text or "").lower()) if len(w) >= 3 and w not in _STOP]


def _concepts(query: str) -> List[List[str]]:
    """The ideas in the query. Every informative word is one idea; every kind of work the vocabulary knows
    (railway, smart city, healthcare ...) is one idea that any of its synonyms satisfies."""
    from app.services.eligibility.domain_vocab import DOMAINS, domains_in
    ideas: List[List[str]] = []
    covered = set()
    for name in domains_in(query):
        aliases = DOMAINS[name]
        ideas.append([a.lower() for a in aliases])
        for a in aliases:
            covered.update(_tokens(a))
    for tok in dict.fromkeys(_tokens(query)):
        if tok not in covered:
            ideas.append([tok])
    return ideas


def _expanded_query(query: str, concepts: List[List[str]]) -> str:
    """What is embedded: the requirement plus the synonyms of the kinds of work it names (helps a short query)."""
    extra = [a for group in concepts if len(group) > 1 for a in group[:6]]
    return (query + (" (" + ", ".join(dict.fromkeys(extra)) + ")" if extra else ""))[:1500]


def _lexical(concepts: List[List[str]], passage_text: str, idf: Dict[str, float]) -> float:
    """0-1: how strongly the passage mentions the query's ideas. A rare word or synonym is strong evidence, a common one weak.
    The evidence adds up ('noisy OR'), so extra words in a long tender sentence do not drown out one strong match."""
    if not concepts:
        return 0.0
    low = passage_text.lower()
    words = set(_tokens(passage_text))
    ceiling = max(idf.values(), default=1.0) or 1.0
    miss = 1.0
    for group in concepts:
        if any((g in low) if " " in g or "-" in g else (g in words or any(w.startswith(g) for w in words)) for g in group):
            weight = max((idf.get(w, ceiling) for g in group for w in _tokens(g)), default=ceiling)
            miss *= 1.0 - min(0.9, 0.9 * weight / ceiling)
    return 1.0 - miss


_KEYWORD_ONLY_MIN = 0.7          # without the embedding model only rare-word / synonym hits are offered


# (cosine of unrelated text, cosine of a strong match) per embedding model, measured on this knowledge base.
# nomic-embed-text: unrelated ~0.45, strong ~0.85.  bge-m3: unrelated ~0.42, strong ~0.70 (it spreads scores over a narrower range).
_COSINE_RANGE = {"bge-m3": (0.42, 0.70), "nomic-embed-text": (0.45, 0.85)}


def _cos_adj(cos: float) -> float:
    """Stretch the cosine between 'unrelated' and 'strong match' for the model in use to a 0-1 score."""
    low, high = _COSINE_RANGE.get((_model() or "").split(":")[0], (0.45, 0.85))
    return max(0.0, min(1.0, (cos - low) / (high - low)))


async def search(db: AsyncSession, query: str, tables: Iterable[str], top_k: int = 8, min_score: float = 0.40,
                 query_vector: Optional[List[float]] = None, use_embedding: bool = True) -> List[Dict[str, Any]]:
    """Rows of `tables` that fit `query`, best first: [{table, id, score, cosine, keywords, text}].

    Hybrid: score = 0.65 x meaning (embedding similarity) + 0.35 x keywords (rare words and synonyms the row mentions).
    If the embedding model cannot be reached the search still works on keywords alone, so retrieval never stops."""
    query = (query or "").strip()
    if not query:
        return []
    passages = list((await db.execute(select(KbPassage).where(KbPassage.source_table.in_(set(tables))))).scalars())
    if not passages:
        return []
    df = Counter(w for p in passages for w in set(_tokens(p.text)))
    n = len(passages)
    idf = {w: math.log(1 + n / c) for w, c in df.items()}
    concepts = _concepts(query)
    vector = query_vector
    if vector is None and use_embedding:
        try:
            vector = await llm_client.embed(_expanded_query(query, concepts))
        except Exception:
            vector = None                                     # keyword-only search below
    hits = []
    for p in passages:
        lex = _lexical(concepts, p.text, idf)
        if vector is not None and p.embedding and len(p.embedding) == len(vector):     # other model / size: never compare
            cos = _cosine(vector, p.embedding)
            score = 0.65 * _cos_adj(cos) + 0.35 * lex
        else:
            cos, score = None, lex                           # keywords alone are a weaker signal: demand a strong word match
        if score >= (min_score if cos is not None else max(min_score, _KEYWORD_ONLY_MIN)):
            hits.append({"table": p.source_table, "id": p.source_id, "score": round(score, 3),
                         "cosine": None if cos is None else round(cos, 3), "keywords": round(lex, 3), "text": p.text})
    return sorted(hits, key=lambda h: -h["score"])[:top_k]


# ── used by the tender analysis ──────────────────────────────────────────────────────────────────────

_PROJECT_FIELDS = {"similar_work_value", "project_value", "contract_count", "govt_psu_experience", "cloud_ops_experience",
                   "software_component_value", "other"}
_ROLE_FIELDS = {"role_qualification", "role_experience_years", "team_role_count", "other"}
# the requirement talks about the KIND of work (not only a number): only then does meaning decide which projects count
_KIND_OF_WORK = re.compile(r"\bsimilar\b|\bexperience\b|\bnature\b|\bsector\b|\bdomain\b|\brelated\b|\bfield\s+of\b|"
                           r"\bprojects?\s+(?:of|in|for|related)\b|\bworks?\s+(?:of|in|for|related)\b|\bimplementation\s+of\b", re.IGNORECASE)
_ABOUT_PEOPLE = re.compile(r"\bteam\b|\bpersonnel\b|\bmanager\b|\barchitect\b|\bdeveloper\b|\banalyst\b|\bengineer\b|\bexpert\b|"
                           r"\bspecialist\b|\bconsultant\b|\bresources?\b|\bmembers?\b|\bcertified\b|\bpmp\b|\bcissp\b", re.IGNORECASE)
_BOILERPLATE = re.compile(r"^\W*(?:the\s+)?(?:bidder|applicant|firm|company|agency|vendor|contractor)\s+(?:should|shall|must)\s+"
                          r"(?:have|possess|be)?\s*", re.IGNORECASE)


def requirement_query(text: str) -> str:
    """The requirement's own wording, trimmed to what describes the work: this is what gets embedded and searched."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = _BOILERPLATE.sub("", t)
    return t[:400]


RERANK_SYSTEM = ("You check whether past company projects fit what a tender asks for. For each numbered project say if it is the "
                 "kind of work the requirement asks for (fits true/false) and give a short reason of at most 15 words that uses only "
                 "words from the project text. Do not judge values or dates. Return JSON only.")
RERANK_SCHEMA = {"type": "object", "properties": {"matches": {"type": "array", "items": {"type": "object", "properties": {
    "n": {"type": "integer"}, "fits": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["n", "fits"]}}}, "required": ["matches"]}


async def rerank(requirement: str, hits: List[Dict[str, Any]], options: Any = None) -> List[Dict[str, Any]]:
    """Ask the model, of the best few hits, which really fit. Hits it rejects are dropped; its reason is kept. Any failure
    (model offline, bad answer) returns the hits unchanged: the search never depends on this step."""
    from app.ai.tender import llm_call
    from app.ai.tender.json_parse import parse_json_robust
    top = hits[:6]
    if len(top) < 2:
        return hits
    listing = "\n".join(f"{i + 1}. {h['text'][:260]}" for i, h in enumerate(top))
    try:
        content = await llm_call.chat_json(RERANK_SYSTEM, f"Requirement: {requirement[:400]}\n\nProjects:\n{listing}", RERANK_SCHEMA,
                                           temperature=0.0, options=options)
        parsed = parse_json_robust(content, required_key="matches")
        rows = parsed.get("matches") if isinstance(parsed, dict) else parsed
        verdict = {int(r["n"]) - 1: r for r in rows if isinstance(r, dict) and str(r.get("n", "")).isdigit()}
    except Exception:
        return hits
    if len(verdict) < len(top) // 2:                         # the answer does not cover the list: do not trust it
        return hits
    kept = []
    for i, h in enumerate(top):
        r = verdict.get(i)
        if r is None or r.get("fits"):
            if r and r.get("reason"):
                h = {**h, "reason": str(r["reason"])[:160]}
            kept.append(h)
    return kept + hits[6:]


async def _matches(db: AsyncSession, criteria: List[Any], fields: set, gate: "re.Pattern[str]", table: str,
                   names: Dict[int, str], options: Any) -> Dict[str, Dict[str, Any]]:
    from app.core.config import settings
    out: Dict[str, Dict[str, Any]] = {}
    for c in criteria:
        if c.field not in fields or not gate.search(c.source_text or ""):
            continue
        query = requirement_query(c.source_text)
        hits = await search(db, query, [table], top_k=8, min_score=settings.KB_SEMANTIC_MIN_SCORE)
        if hits and settings.KB_SEMANTIC_RERANK:
            hits = await rerank(query, hits, options)
        found = [h for h in hits if h["id"] in names]
        if found:
            out[c.criterion_id] = {"names": [names[h["id"]] for h in found],
                                   "reasons": {names[h["id"]]: h.get("reason") for h in found if h.get("reason")}}
    return out


async def semantic_matches(db: AsyncSession, criteria: List[Any], options: Any = None) -> Dict[str, Dict[str, Any]]:
    """{criterion id: {"projects": {names, reasons}, "employees": {names, reasons}}} for requirements that describe a kind of
    work or kind of person. The query is the requirement's own sentence. Never raises: no index, no embedding model or no hit
    simply means no help (keyword search still runs)."""
    from app.core.config import settings
    if not settings.KB_SEMANTIC_MATCH:
        return {}
    try:
        proj = {p.id: p.name for p in (await db.execute(select(Project))).scalars()}
        emps = {e.id: e.name for e in (await db.execute(select(Employee))).scalars()}
        by_proj = await _matches(db, criteria, _PROJECT_FIELDS, _KIND_OF_WORK, "projects", proj, options)
        by_emp = await _matches(db, criteria, _ROLE_FIELDS, _ABOUT_PEOPLE, "employees", emps, options)
        out: Dict[str, Dict[str, Any]] = {}
        for cid, v in by_proj.items():
            out.setdefault(cid, {})["projects"] = v
        for cid, v in by_emp.items():
            out.setdefault(cid, {})["employees"] = v
        return out
    except Exception:
        return {}
