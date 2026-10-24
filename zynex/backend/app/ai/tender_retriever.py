"""
TenderRetriever — semantic search over TenderChunk rows for a specific document.

Used by eligibility and estimation engines to retrieve the most relevant
sections of the uploaded tender document for a given query.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.ai.llm_client import llm_client, OllamaUnavailableError


class TenderRetriever:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def retrieve(
        self,
        query: str,
        document_id: int,
        top_k: int = 5,
    ) -> list[dict]:
        """
        Embed `query`, then cosine-search tender_chunks for `document_id`.
        Falls back to returning the first `top_k` chunks by index if embeddings
        are unavailable.
        """
        try:
            import json, math

            query_vec = await llm_client.embed(query)

            sql = text(
                """
                SELECT id, chunk_index, chunk_text, section_heading, embedding
                FROM tender_chunks
                WHERE document_id = :doc_id
                  AND embedding IS NOT NULL
                """
            )
            result = await self.db.execute(sql, {"doc_id": document_id})
            rows = result.mappings().all()

            def _cosine(a, b):
                if len(a) != len(b):      # vectors from a different embedding model cannot be compared
                    return 0.0
                dot = sum(x * y for x, y in zip(a, b))
                ma = math.sqrt(sum(x * x for x in a))
                mb = math.sqrt(sum(x * x for x in b))
                return dot / (ma * mb) if ma and mb else 0.0

            scored = []
            for row in rows:
                try:
                    emb = json.loads(row["embedding"]) if isinstance(row["embedding"], str) else row["embedding"]
                    sim = _cosine(query_vec, emb)
                    scored.append({
                        "id": row["id"],
                        "chunk_index": row["chunk_index"],
                        "chunk_text": row["chunk_text"],
                        "section_heading": row["section_heading"],
                        "similarity": round(sim, 4),
                    })
                except Exception:
                    continue

            if scored:
                scored.sort(key=lambda x: x["similarity"], reverse=True)
                return scored[:top_k]
        except Exception:
            pass

        # Fallback: return first top_k chunks ordered by index
        fallback_sql = text(
            """
            SELECT id, chunk_index, chunk_text, section_heading
            FROM tender_chunks
            WHERE document_id = :doc_id
            ORDER BY chunk_index
            LIMIT :k
            """
        )
        result = await self.db.execute(
            fallback_sql, {"doc_id": document_id, "k": top_k}
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    async def retrieve_for_criteria(
        self,
        criteria_list: list[str],
        document_id: int,
        top_k_per_criterion: int = 3,
    ) -> dict[str, list[dict]]:
        """Retrieve relevant chunks per criterion (used by eligibility engine)."""
        results: dict[str, list[dict]] = {}
        for criterion in criteria_list:
            chunks = await self.retrieve(criterion, document_id, top_k=top_k_per_criterion)
            results[criterion] = chunks
        return results
