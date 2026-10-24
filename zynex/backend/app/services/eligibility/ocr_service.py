try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 preferred import
except ImportError:
    import fitz  # fallback for older pymupdf installs
import io
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.eligibility.pipeline_log import log_pipeline_step

# Tesseract's script name (from orientation/script detection) -> language packs that read it, best first. Indian
# languages and English only. Hindi reads Marathi, Nepali and Sanskrit well (same Devanagari script), Bengali reads Assamese.
SCRIPT_LANGUAGES = {
    "Latin": ["eng"], "Devanagari": ["hin", "mar", "nep", "san"], "Tamil": ["tam"], "Telugu": ["tel"], "Kannada": ["kan"],
    "Malayalam": ["mal"], "Bengali": ["ben", "asm"], "Gujarati": ["guj"], "Gurmukhi": ["pan"], "Oriya": ["ori"],
    "Arabic": ["urd"],
}
# When a page reads badly, one installed pack per script is tried, in this order (most common in tenders first).
TRY_FAMILIES = [["hin", "mar", "nep", "san"], ["tam"], ["tel"], ["kan"], ["mal"], ["ben", "asm"], ["guj"], ["pan"], ["ori"], ["urd"]]
MAX_PACKS_TRIED = len(TRY_FAMILIES)
GOOD_CONFIDENCE = 85     # a candidate this good ends the search
STOP_SEARCHING_AFTER = 2  # pages in a row where searching other languages found nothing better
LANGUAGE_PACKAGE = "tesseract-ocr-{lang}"      # the Debian/Ubuntu package that installs a pack


class OCRSession:
    """Remembers, within one document, which language worked and whether searching other languages is paying off, so a
    300-page Tamil scan does not repeat the language search on every page."""

    def __init__(self) -> None:
        self.hint: Optional[str] = None       # languages that read the last page well
        self.fruitless = 0                    # consecutive low-confidence pages where no other language did better

    @property
    def search_enabled(self) -> bool:
        return self.fruitless < STOP_SEARCHING_AFTER


class OCRService:
    """S2b OCR for scanned pages. Local Tesseract only (offline; no model downloads)."""

    LOW_CONFIDENCE = 70  # mean word confidence (%) under which other language packs are tried and the page is flagged
    RENDER_SCALE = 3  # ~216 dpi: Tesseract is noticeably less accurate below ~200 dpi

    # ------------------------------------------------------------------ languages
    @staticmethod
    def _tess_config() -> str:
        folder = (settings.OCR_TESSDATA_DIR or "").strip()
        return f'--tessdata-dir "{folder}"' if folder else ""

    @classmethod
    def _all_languages(cls) -> List[str]:
        """Every pack Tesseract lists (asked of the binary itself: pytesseract.get_languages leaves out capitalised
        script packs)."""
        import shlex
        import subprocess
        try:
            import pytesseract
            cmd = [pytesseract.pytesseract.tesseract_cmd, "--list-langs"] + shlex.split(cls._tess_config())
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True).stdout
            return [l.strip() for l in out.splitlines()[1:] if l.strip()]
        except Exception as ex:
            log_pipeline_step("S2B_OCR_SERVICE", status="WARNING", message=f"cannot list OCR languages: {ex}")
            return []

    @classmethod
    def installed_languages(cls) -> List[str]:
        """Language packs Tesseract can use right now (system folder, or the folder set on the Settings page)."""
        return [l for l in cls._all_languages() if l != "osd"]

    @classmethod
    def choose_languages(cls, image=None) -> Tuple[str, List[str]]:
        """('tam+eng', notes): the configured languages that are installed, plus the language of the page's own script
        when script detection can tell. notes explain what could not be done (a pack that is not installed)."""
        installed = set(cls.installed_languages())
        notes: List[str] = []
        wanted = [l for l in re.split(r"[+,\s]+", settings.OCR_LANGUAGES or "eng") if l] or ["eng"]
        if settings.OCR_AUTO_SCRIPT and image is not None and "osd" in cls._all_languages():
            lang = next((l for l in SCRIPT_LANGUAGES.get(cls._detect_script(image) or "", []) if l in installed), None)
            if lang and lang not in wanted:
                wanted.insert(0, lang)
        usable = [l for l in dict.fromkeys(wanted) if l in installed]
        for l in dict.fromkeys(wanted):
            if l not in installed:
                notes.append(f"OCR language '{l}' is not installed (package {LANGUAGE_PACKAGE.format(lang=l)}, or set the "
                             "folder under Settings > Tender Analysis)")
        return "+".join(usable or ["eng"]), notes

    @classmethod
    def _ocr(cls, image, lang: str) -> Tuple[str, float]:
        """(text, mean word confidence 0-100). A poor or empty first reading is repeated in block mode (psm 6), because
        automatic page layout gives up on sparse pages ('Empty page!') and on some scripts; the better reading wins."""
        text, conf = cls._ocr_pass(image, lang, "")
        if conf < cls.LOW_CONFIDENCE:
            text2, conf2 = cls._ocr_pass(image, lang, "--psm 6")
            if conf2 > conf:
                return text2, conf2
        return text, conf

    @classmethod
    def _ocr_pass(cls, image, lang: str, extra: str) -> Tuple[str, float]:
        """One Tesseract pass. Paragraphs are kept (a blank line between them)."""
        import pytesseract
        config = f"{cls._tess_config()} {extra}".strip()
        data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
        paragraphs: Dict[Tuple[int, int], Dict[int, List[str]]] = {}
        confs: List[float] = []
        for i, word in enumerate(data["text"]):
            if not str(word).strip():
                continue
            key = (data["block_num"][i], data["par_num"][i])
            paragraphs.setdefault(key, {}).setdefault(data["line_num"][i], []).append(word)
            try:
                c = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if c >= 0:
                confs.append(c)
        text = "\n\n".join("\n".join(" ".join(words) for _n, words in sorted(lines.items()))
                           for _k, lines in sorted(paragraphs.items()))
        return text, (sum(confs) / len(confs) if confs else 0.0)

    @staticmethod
    def _ink_band(image):
        """The top part of the area that holds ink (not the white margin), for a quick test of a candidate language."""
        gray = image.convert("L").point(lambda v: 255 if v < 200 else 0)
        box = gray.getbbox() or (0, 0, image.size[0], image.size[1])
        left, top, right, bottom = box
        return image.crop((left, top, right, min(image.size[1], top + max(400, int(0.35 * (bottom - top))))))

    @classmethod
    def read_page(cls, image, session: Optional[OCRSession] = None) -> Tuple[str, str, float, List[str]]:
        """(text, languages used, confidence, notes). One pass normally. When the result is poor, one installed pack
        per script family is tried on a slice of the page and the page is re-read with the best one, so a Tamil or Hindi
        page is not left as English-alphabet garbage. `session` carries what worked on earlier pages."""
        session = session or OCRSession()
        languages, notes = cls.choose_languages(image)
        if session.hint and session.hint not in languages:
            languages = session.hint                      # the language that read the previous pages of this document
        text, conf = cls._ocr(image, languages)
        if conf < cls.LOW_CONFIDENCE and session.search_enabled:
            installed = cls.installed_languages()
            tried = set(languages.split("+"))
            candidates = []
            for family in TRY_FAMILIES:
                pack = next((l for l in family if l in installed), None)
                if pack and pack not in tried and not any(f in tried for f in family):
                    candidates.append(pack)
            band = cls._ink_band(image)
            best_conf, best = 0.0, None
            for pack in candidates[:MAX_PACKS_TRIED]:
                # block mode: reads a slice reliably in every script. A reading of two characters is not evidence, so
                # confidence is weighed by how much text was actually read.
                band_text, c = cls._ocr_pass(band, f"{pack}+eng" if "eng" in installed else pack, "--psm 6")
                c *= min(1.0, len(re.sub(r"\s", "", band_text)) / 20)
                if c > best_conf:
                    best_conf, best = c, pack
                if c >= GOOD_CONFIDENCE:
                    break
            if best and best_conf >= conf + 10:
                better_lang = f"{best}+eng" if "eng" in installed else best
                better_text, better_conf = cls._ocr(image, better_lang)
                if better_conf > conf:
                    text, languages, conf = better_text, better_lang, better_conf
                    session.fruitless = 0
            else:
                session.fruitless += 1
        if conf >= cls.LOW_CONFIDENCE:
            session.hint = languages if languages != "eng" else session.hint
        if conf < cls.LOW_CONFIDENCE:
            notes.append(f"OCR confidence is low ({conf:.0f}%) with languages {languages}; check this page against the original")
        return text, languages, conf, notes

    @classmethod
    def _detect_script(cls, image) -> Optional[str]:
        try:
            import pytesseract
            osd = pytesseract.image_to_osd(image, config=cls._tess_config(), output_type=pytesseract.Output.DICT)
            return osd.get("script")
        except Exception:                       # too little text to judge, or no osd data: keep the configured languages
            return None

    @classmethod
    def process_scanned_page(cls, pdf_bytes: bytes, page_no: int, session: Optional[OCRSession] = None) -> Dict[str, Any]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            page_index = page_no - 1
            if page_index < 0 or page_index >= len(doc):
                return {"page_no": page_no, "blocks": [], "char_count": 0, "ocr_used": False}

            page = doc[page_index]
            raw_page_text = page.get_text()
            pix = page.get_pixmap(matrix=fitz.Matrix(cls.RENDER_SCALE, cls.RENDER_SCALE))
            img_bytes = pix.tobytes("png")

            blocks = []
            ocr_used = False
            languages, notes, confidence = "eng", [], 0.0
            try:
                from PIL import Image
                image = Image.open(io.BytesIO(img_bytes))
                ocr_text, languages, confidence, notes = cls.read_page(image, session)
                blocks = cls._blocks(ocr_text)
                ocr_used = bool(blocks)
            except Exception as ex:
                log_pipeline_step("S2B_OCR_SERVICE", page_no=page_no, status="WARNING",
                                  message=f"Tesseract OCR error: {ex}")

            if not blocks and raw_page_text.strip():
                blocks = cls._blocks(raw_page_text)  # embedded text is better than nothing

            total_chars = sum(len(b["text"]) for b in blocks)
            log_pipeline_step("S2B_OCR_SERVICE", page_no=page_no, status="SUCCESS",
                              message=f"OCR processed page {page_no}: {total_chars} chars extracted")
            return {"page_no": page_no, "blocks": blocks, "char_count": total_chars, "ocr_used": ocr_used,
                    "languages": languages, "notes": notes, "confidence": round(confidence, 1)}
        finally:
            doc.close()

    @classmethod
    def _blocks(cls, text: str) -> list:
        """One block per paragraph (blank-line separated), with a synthetic top-to-bottom position.

        A single block for the whole page would hide every heading and clause number except the first
        line from the structure analyzer (S3).
        """
        import re
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
        if len(paragraphs) <= 1:  # no blank lines: fall back to one block per line
            paragraphs = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        out = []
        for i, para in enumerate(paragraphs):
            block = cls._block(para)
            block["y0"] = i
            block["bbox"] = (0, i, 100, i + 1)
            out.append(block)
        return out

    @staticmethod
    def _block(text: str) -> Dict[str, Any]:
        return {"bbox": (0, 0, 100, 100), "y0": 0, "x0": 0, "text": text.strip(),
                "is_heading": False, "type": "text"}
