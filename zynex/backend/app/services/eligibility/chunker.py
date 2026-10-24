from typing import List, Dict, Any
from app.schemas.eligibility import ChunkSchema
from app.services.eligibility.pipeline_log import log_pipeline_step
from app.services.eligibility.errors import PipelineError

class Chunker:
    """
    S4 Page-Based Line Chunker:
    Groups document text by PDF physical page, formatting text line-by-line with page context.
    Eliminates micro-fragmentation and creates clean, coherent page-level chunks for LLM evaluation.
    """

    MAX_CHUNK_CHARS = 3000
    MAX_ROW_CHARS = 8000        # a single table row is never cut below this length
    EMPTY_PAGE_NOTE = "No extracted text on this page."

    @classmethod
    def create_chunks(cls, run_id: str, structured_nodes: List[Dict[str, Any]], total_pages: int) -> List[ChunkSchema]:
        chunks: List[ChunkSchema] = []
        seq_by_page: Dict[int, int] = {}

        def get_next_chunk_id(p_no: int) -> str:
            seq = seq_by_page.get(p_no, 0) + 1
            seq_by_page[p_no] = seq
            return f"ck_{run_id[:8]}_{p_no:03d}_{seq:03d}"

        try:
            # Group structured nodes by physical page
            page_nodes_map: Dict[int, List[Dict[str, Any]]] = {}
            for node in structured_nodes:
                if not isinstance(node, dict):
                    continue
                p_no = int(node.get("page_no") or node.get("physical_page") or 1)
                page_nodes_map.setdefault(p_no, []).append(node)

            total_pages_safe = max(1, total_pages, max(page_nodes_map.keys(), default=1))

            for p_no in range(1, total_pages_safe + 1):
                nodes = page_nodes_map.get(p_no, [])
                if not nodes:
                    # Fallback empty page chunk
                    chunks.append(ChunkSchema(
                        chunk_id=get_next_chunk_id(p_no),
                        run_id=run_id,
                        physical_page=p_no,
                        source_pages=[p_no],
                        chapter="General Specification",
                        section=f"Page {p_no}",
                        clause=None,
                        content_type="page_text",
                        chunk_text=f"--- [PAGE {p_no}] ---\n{cls.EMPTY_PAGE_NOTE}",
                        char_count=len(f"--- [PAGE {p_no}] ---\n{cls.EMPTY_PAGE_NOTE}"),
                        is_scanned=False,
                        ocr_used=False
                    ))
                    continue

                header = f"--- [PAGE {p_no}] ---"
                units = [(n, cls._render(n)) for n in nodes]
                units = [(n, t) for n, t in units if t]

                # Pack whole clauses/tables into chunks of at most MAX_CHUNK_CHARS; a unit is only cut
                # (at line level) when it is longer than the limit on its own.
                groups: List[List[Dict[str, Any]]] = []
                texts: List[str] = []
                cur_nodes: List[Dict[str, Any]] = []
                cur_parts: List[str] = []
                cur_len = len(header)
                for node, text in units:
                    pieces = [text] if len(text) + len(header) + 1 <= cls.MAX_CHUNK_CHARS \
                        else cls._split_page_text(text, cls.MAX_CHUNK_CHARS - len(header) - 1)
                    for piece in pieces:
                        if cur_parts and cur_len + len(piece) + 1 > cls.MAX_CHUNK_CHARS:
                            groups.append(cur_nodes)
                            texts.append("\n".join([header] + cur_parts))
                            cur_nodes, cur_parts, cur_len = [], [], len(header)
                        cur_nodes.append(node)
                        cur_parts.append(piece)
                        cur_len += len(piece) + 1
                if cur_parts:
                    groups.append(cur_nodes)
                    texts.append("\n".join([header] + cur_parts))

                for group, page_text in zip(groups, texts):
                    # chapter / section / clause shown for a chunk come from the nodes it actually contains
                    p_chapter = next((n.get("chapter") for n in group if n.get("chapter")), f"Page {p_no}")
                    p_section = next((n.get("section") for n in group
                                      if n.get("section") and n.get("section") != p_chapter), f"Section Page {p_no}")
                    p_clause = next((n.get("clause") for n in group if n.get("clause")), None)
                    chunks.append(ChunkSchema(
                        chunk_id=get_next_chunk_id(p_no),
                        run_id=run_id,
                        physical_page=p_no,
                        source_pages=[p_no],
                        chapter=p_chapter,
                        section=p_section,
                        clause=p_clause,
                        content_type="table" if all(n.get("type") == "table" for n in group) else "page_text",
                        chunk_text=page_text,
                        char_count=len(page_text),
                        is_scanned=any(n.get("is_scanned") for n in group),
                        ocr_used=any(n.get("ocr_used") for n in group),
                    ))

            log_pipeline_step("S4_CHUNKER", status="SUCCESS", message=f"Created {len(chunks)} page chunks covering {total_pages_safe} pages")
            return chunks

        except Exception as e:
            log_pipeline_step("S4_CHUNKING_ERROR", run_id=run_id, status="FAILED", message=f"S4 Chunker exception: {str(e)}")
            raise PipelineError(f"S4 Chunker failed for run {run_id}: {str(e)}") from e

    @staticmethod
    def _render(node: Dict[str, Any]) -> str:
        if node.get("type") == "table":
            text_repr = str(node.get("text_repr", "") or "").strip()
            return f"[TABLE START]\n{text_repr}\n[TABLE END]" if text_repr else ""
        return str(node.get("text", "") or "").strip()

    @classmethod
    def _split_page_text(cls, text: str, max_chars: int) -> List[str]:
        """Split at line boundaries; a single over-long line is wrapped at the last space. A [TABLE START] /
        [TABLE END] marker never ends up alone in a chunk."""
        lines: List[str] = []
        for line in text.split("\n"):
            # a table row is one requirement: keep it whole (up to a hard ceiling) rather than cut it mid-sentence
            row_like = " | " in line and not line.startswith("|")
            limit = cls.MAX_ROW_CHARS if row_like else max_chars
            while len(line) > limit:
                cut = line.rfind(" ", 0, limit)
                cut = cut if cut > limit // 2 else limit
                lines.append(line[:cut].rstrip())
                line = line[cut:].lstrip()
            lines.append(line)

        sub_chunks: List[str] = []
        cur: List[str] = []
        cur_len = 0
        for line in lines:
            if cur_len + len(line) + 1 > max_chars and cur:
                if cur[-1].strip() == "[TABLE START]":          # keep the opening marker with its first row
                    marker = cur.pop()
                    sub_chunks.append("\n".join(cur)) if cur else None
                    cur, cur_len = [marker], len(marker) + 1
                else:
                    sub_chunks.append("\n".join(cur))
                    cur, cur_len = [], 0
            cur.append(line)
            cur_len += len(line) + 1
        if cur:
            if len(cur) == 1 and cur[0].strip() == "[TABLE END]" and sub_chunks:
                sub_chunks[-1] += "\n" + cur[0]               # a closing marker alone joins the previous chunk
            else:
                sub_chunks.append("\n".join(cur))
        return [c for c in sub_chunks if c.strip()]
