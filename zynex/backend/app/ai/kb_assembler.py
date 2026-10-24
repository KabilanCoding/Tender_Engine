"""
KBAssembler — assembles company context for LLM prompts from three layers:
  Layer 1: PostgreSQL structured facts (certs, financials, rates)
  Layer 2: past projects with their clients and technologies (PostgreSQL)
  Layer 3: semantic search over uploaded project documents (top-K chunks)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.knowledge_base import Client, Project, Certification, CostParameter
from app.models.project_documents import ProjectDocumentChunk, FinancialRecord
from app.ai.llm_client import llm_client, OllamaUnavailableError


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class KBContext:
    """All assembled context passed to prompt builder."""
    company_name: str = "ZYNEX"
    certifications: list[dict] = field(default_factory=list)
    financials: list[dict] = field(default_factory=list)
    past_projects: list[dict] = field(default_factory=list)       # completed projects
    relevant_chunks: list[dict] = field(default_factory=list)     # semantic search hits
    cost_parameters: list[dict] = field(default_factory=list)


# ── KBAssembler ───────────────────────────────────────────────────────────────

class KBAssembler:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Layer 1: PostgreSQL ────────────────────────────────────────────────────

    async def get_base_profile(self) -> dict:
        """Return structured facts: certs + latest 3 financial years."""
        certs_result = await self.db.execute(select(Certification))
        certs = [
            {
                "name": c.name,
                "issuing_body": c.issuing_body,
                "valid_until": c.valid_until,
            }
            for c in certs_result.scalars().all()
        ]

        fin_result = await self.db.execute(
            select(FinancialRecord).order_by(FinancialRecord.fiscal_year.desc()).limit(3)
        )
        financials = [
            {
                "fiscal_year": f.fiscal_year,
                "annual_turnover": f.annual_turnover,
                "currency": f.currency,
            }
            for f in fin_result.scalars().all()
        ]

        return {"certifications": certs, "financials": financials}

    async def get_cost_parameters(self) -> list[dict]:
        result = await self.db.execute(select(CostParameter))
        return [
            {
                "role": c.role,
                "level": c.level,
                "hourly_rate": c.hourly_rate,
            }
            for c in result.scalars().all()
        ]

    # ── Layer 2: past projects ────────────────────────────────────────────────

    async def past_projects(self, limit: int = 5) -> list[dict]:
        """Most recent completed projects with their client and technologies."""
        result = await self.db.execute(
            select(Project, Client.name)
            .outerjoin(Client, Client.id == Project.client_id)
            .where(Project.status == "completed")
            .order_by(Project.id.desc())
            .limit(limit)
        )
        return [
            {"id": p.id, "name": p.name, "client": client_name, "technologies": list(p.technologies or [])}
            for p, client_name in result.all()
        ]

    # ── Layer 3: semantic search ─────────────────────────────────────

    async def semantic_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Embed query → cosine similarity in Python → return top-K chunks."""
        import json, math

        try:
            query_vec = await llm_client.embed(query)
        except OllamaUnavailableError:
            return []

        # Fetch all chunks that have embeddings
        sql = text(
            """
            SELECT id, project_id, chunk_text, section_heading, doc_category, embedding
            FROM project_document_chunks
            WHERE embedding IS NOT NULL
            """
        )
        result = await self.db.execute(sql)
        rows = result.mappings().all()

        def cosine_similarity(a: list, b: list) -> float:
            if len(a) != len(b):      # vectors from a different embedding model cannot be compared
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(x * x for x in b))
            if mag_a == 0 or mag_b == 0:
                return 0.0
            return dot / (mag_a * mag_b)

        scored = []
        for row in rows:
            try:
                emb = json.loads(row["embedding"]) if isinstance(row["embedding"], str) else row["embedding"]
                sim = cosine_similarity(query_vec, emb)
                scored.append({
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "chunk_text": row["chunk_text"],
                    "section_heading": row["section_heading"],
                    "doc_category": row["doc_category"],
                    "similarity": round(sim, 4),
                })
            except Exception:
                continue

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    # ── Assembled context for specific use-cases ──────────────────────────────

    async def assemble_for_eligibility(self, criterion_text: str) -> KBContext:
        """
        Build context for one eligibility criterion check.
        Retrieves certs/financials + semantically similar document chunks.
        """
        base = await self.get_base_profile()
        chunks = await self.semantic_search(criterion_text, top_k=5)
        graph_projects = await self.past_projects(limit=5)

        return KBContext(
            certifications=base["certifications"],
            financials=base["financials"],
            past_projects=graph_projects,
            relevant_chunks=chunks,
        )

    async def assemble_for_estimation(self, requirement_text: str) -> KBContext:
        """
        Build context for project estimation.
        Retrieves cost rates + similar past project scope docs.
        """
        base = await self.get_base_profile()
        chunks = await self.semantic_search(requirement_text, top_k=5)
        cost_params = await self.get_cost_parameters()
        graph_projects = await self.past_projects(limit=5)

        return KBContext(
            certifications=base["certifications"],
            financials=base["financials"],
            past_projects=graph_projects,
            relevant_chunks=chunks,
            cost_parameters=cost_params,
        )
