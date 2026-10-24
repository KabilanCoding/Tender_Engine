try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 preferred import
except ImportError:
    import fitz  # fallback for older pymupdf installs
from typing import List, Dict, Any, Tuple
from app.services.eligibility.pipeline_log import log_pipeline_step

class PDFExtractor:
    """
    S2a PDF Extractor using PyMuPDF (fitz).

    Text blocks are returned in reading order. Ruled tables are detected with PyMuPDF's table finder and
    emitted as one pipe-delimited block per table (header row first), so S3 can rebuild rows and the LLM
    sees each requirement row intact instead of cells scattered across blocks.
    """

    MARGIN = 0.08            # top/bottom share of the page treated as header/footer zone
    MARGIN_MAX_CHARS = 150   # only short blocks inside the margin are dropped (page numbers, running titles)

    @staticmethod
    def _cell(value) -> str:
        return " ".join(str(value or "").replace("|", "/").split())

    @classmethod
    def _find_tables(cls, page) -> List[Dict[str, Any]]:
        """[{bbox, text}] for each table with >= 2 rows and >= 2 columns; never raises."""
        found: List[Dict[str, Any]] = []
        try:
            if len(page.get_cdrawings()) < 4:          # no ruled lines: no ruled table, skip the slow finder
                return found
            # 'lines_strict' reads a ruled table by its visible lines only; the default strategy also guesses column edges from
            # text and can split one table into a dozen phantom columns and merge neighbouring rows (seen on 4-column
            # eligibility tables). Use the strict result, and add default-strategy tables only where strict found none there.
            strict = []
            try:
                strict = list(page.find_tables(strategy="lines_strict").tables)
            except Exception:
                strict = []
            default = list(page.find_tables().tables)

            def overlap(a, b) -> float:
                x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
                inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
                area = max(1.0, min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])))
                return inter / area

            chosen = list(strict) + [t for t in default if not any(overlap(tuple(t.bbox), tuple(u.bbox)) > 0.5 for u in strict)]
            for t in chosen:
                rows = [[cls._cell(c) for c in r] for r in t.extract()]
                rows = [r for r in rows if any(r)]
                if rows:                                   # drop columns that are empty in every row
                    width0 = max(len(r) for r in rows)
                    keep = [i for i in range(width0) if any(i < len(r) and r[i] for r in rows)]
                    rows = [[r[i] if i < len(r) else "" for i in keep] for r in rows]
                if len(rows) < 2 or (rows and max(len(r) for r in rows) < 2):
                    continue
                width = max(len(r) for r in rows)
                lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
                lines.insert(1, "|" + "---|" * width)
                found.append({"bbox": tuple(t.bbox), "text": "\n".join(lines)})
        except Exception as ex:
            log_pipeline_step("S2A_PDF_EXTRACTOR", status="WARNING", message=f"table detection failed: {ex}")
        return found

    @staticmethod
    def _inside(bbox, table_bbox, tol: float = 2.0) -> bool:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        return (table_bbox[0] - tol <= cx <= table_bbox[2] + tol) and (table_bbox[1] - tol <= cy <= table_bbox[3] + tol)

    @staticmethod
    def _image_cover(page) -> float:
        """Share of the page area covered by images (a scanned page is mostly one big image)."""
        try:
            area = max(1.0, page.rect.width * page.rect.height)
            covered = 0.0
            for img in page.get_images(full=True):
                for r in page.get_image_rects(img[0]):
                    covered += r.width * r.height
            return min(1.0, covered / area)
        except Exception:
            return 0.0

    @staticmethod
    def _drop_running_headers(pages_data: List[Dict[str, Any]]) -> None:
        """Remove short blocks in the top/bottom margin that REPEAT across pages (letterheads, page numbers,
        tender numbers). A margin block that appears on few pages is real content (a clause, a heading) and stays."""
        import re
        def norm(t: str) -> str:
            return re.sub(r"\d+", "#", re.sub(r"\s+", " ", t.strip().lower()))
        counts: Dict[str, int] = {}
        for p in pages_data:
            for key in {norm(b["text"]) for b in p["blocks"] if b.get("margin")}:
                counts[key] = counts.get(key, 0) + 1
        total = len(pages_data)
        threshold = max(3, int(0.3 * total))
        for p in pages_data:
            keep = []
            for b in p["blocks"]:
                if b.get("margin"):
                    repeated = counts.get(norm(b["text"]), 0) >= threshold
                    if repeated or (total < 4 and len(b["text"]) <= 150 and re.fullmatch(r"[\W\d\s]*(page\s*)?\d*[\W\d\s]*", b["text"].lower())):
                        continue
                b.pop("margin", None)
                keep.append(b)
            p["blocks"] = keep

    @classmethod
    def extract_pdf_data(cls, pdf_bytes: bytes) -> Dict[str, Any]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_data = []

        for page_index in range(len(doc)):
            page = doc[page_index]
            page_no = page_index + 1
            rect = page.rect
            page_height = rect.height

            # Extract raw block dicts
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])

            extracted_blocks = []
            total_chars = 0

            # First pass: compute average font size across text lines
            font_sizes = []
            for b in blocks:
                if b.get("type") == 0:  # Text block
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            font_sizes.append(span.get("size", 10.0))
                            total_chars += len(span.get("text", "").strip())

            body_avg_font = (sum(font_sizes) / len(font_sizes)) if font_sizes else 10.0

            tables = cls._find_tables(page)

            # Second pass: extract blocks while discarding headers/footers
            for b in blocks:
                if b.get("type") == 0:  # Text block
                    r = fitz.Rect(b.get("bbox", (0, 0, 0, 0))) * page.rotation_matrix   # upright coordinates
                    bbox = (r.x0, r.y0, r.x1, r.y1)
                    y0, y1 = bbox[1], bbox[3]

                    # Text already captured inside a detected table is emitted once, as the table
                    if any(cls._inside(bbox, t["bbox"]) for t in tables):
                        continue

                    block_text_lines = []
                    is_heading = False

                    for line in b.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            text = span.get("text", "")
                            font_size = span.get("size", 10.0)
                            flags = span.get("flags", 0)
                            is_bold = bool(flags & (1 << 4) or flags & (1 << 1) or "bold" in span.get("font", "").lower())

                            if font_size > body_avg_font * 1.2 and is_bold:
                                is_heading = True
                            line_text += text
                        if line_text.strip():
                            block_text_lines.append(line_text.strip())

                    full_block_text = "\n".join(block_text_lines).strip()

                    # Strip running headers/footers: short blocks lying entirely inside the top/bottom margin.
                    # (A long body block that merely reaches the margin must not be thrown away.)
                    in_margin = ((y1 < page_height * cls.MARGIN or y0 > page_height * (1 - cls.MARGIN))
                                 and len(full_block_text) <= cls.MARGIN_MAX_CHARS)
                    if full_block_text:
                        extracted_blocks.append({
                            "bbox": bbox,
                            "y0": y0,
                            "x0": bbox[0],
                            "text": full_block_text,
                            "is_heading": is_heading,
                            "type": "text",
                            "margin": in_margin,
                        })

            for t in tables:
                extracted_blocks.append({"bbox": t["bbox"], "y0": t["bbox"][1], "x0": t["bbox"][0],
                                         "text": t["text"], "is_heading": False, "type": "table"})

            # Sort blocks by (bbox.y0, bbox.x0) to preserve reading order
            extracted_blocks.sort(key=lambda x: (x["y0"], x["x0"]))

            body_chars = sum(len(x["text"]) for x in extracted_blocks if not x.get("margin"))
            is_scanned = total_chars < 80 or (body_chars < 400 and cls._image_cover(page) > 0.5)

            pages_data.append({
                "page_no": page_no,
                "blocks": extracted_blocks,
                "char_count": total_chars,
                "is_scanned": is_scanned,
                "has_images": bool(page.get_images()) if is_scanned else False,
                "page_height": page_height
            })

            log_pipeline_step(
                "S2A_PDF_EXTRACTOR",
                page_no=page_no,
                status="SCANNED" if is_scanned else "SUCCESS",
                message=f"Extracted page {page_no}: {total_chars} chars, {len(extracted_blocks)} blocks"
            )

        doc.close()
        cls._drop_running_headers(pages_data)
        return {
            "total_pages": len(pages_data),
            "pages": pages_data
        }
