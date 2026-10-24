try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 preferred
except ImportError:
    import fitz  # fallback for older pymupdf
from typing import List, Tuple, Dict, Any
from app.core.config import settings
from app.services.eligibility.multilingual import TENDER_TERMS, count_terms
from app.services.eligibility.errors import FileValidationError
from app.services.eligibility.pipeline_log import log_pipeline_step

class FileValidator:
    MIN_SIZE_BYTES = 1024            # 1 KB: a one-page corrigendum is only a few KB; the text gate decides the rest

    @classmethod
    def max_size_bytes(cls) -> int:
        return settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    # .docx is not supported: PDFExtractor reads raw PDF bytes only.
    # Removed from ALLOWED_EXTENSIONS to prevent advertising an unsupported format.
    # Implement python-docx extraction before re-adding .docx here.
    ALLOWED_EXTENSIONS = {".pdf"}

    @classmethod
    def validate_file(cls, filename: str, content: bytes, run_id: str = None) -> Dict[str, Any]:
        """
        Validates file extension, size, and checks for encryption/password protection.
        """
        if not filename:
            raise FileValidationError("Filename cannot be empty", run_id=run_id)

        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()

        if ext not in cls.ALLOWED_EXTENSIONS:
            raise FileValidationError(
                f"Unsupported file type '{ext}'. Only PDF files are accepted. "
                "(DOCX support is planned but not yet implemented.)",
                run_id=run_id
            )

        file_size = len(content)
        if file_size < cls.MIN_SIZE_BYTES:
            raise FileValidationError(
                f"File size ({file_size} bytes) is below minimum required 1KB.",
                run_id=run_id
            )

        if file_size > cls.max_size_bytes():
            raise FileValidationError(
                f"File size exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
                run_id=run_id
            )

        if ext == ".pdf":
            try:
                doc = fitz.open(stream=content, filetype="pdf")
                if doc.is_encrypted:
                    raise FileValidationError("PDF file is password-protected or encrypted.", run_id=run_id)
                
                # S1 Step 0: Heuristic tender document validation
                is_tender, reason, score = cls._is_tender_document(doc, filename=filename)
                doc.close()
                if not settings.TENDER_GATE_ENABLED:
                    is_tender = True

                if not is_tender:
                    raise FileValidationError(
                        f"Sorry, please upload a valid tender document. "
                        f"The file '{filename}' was rejected because: {reason}.",
                        run_id=run_id
                    )
            except fitz.FileDataError:
                raise FileValidationError("Sorry, please upload a valid tender document. The PDF file is corrupted or unreadable.", run_id=run_id)
            except Exception as e:
                if isinstance(e, FileValidationError):
                    raise e
                raise FileValidationError(f"Sorry, please upload a valid tender document. Error reading file: {str(e)}", run_id=run_id)

        log_pipeline_step("S1_FILE_VALIDATOR", status="SUCCESS", message=f"Validated {filename} ({file_size} bytes)")
        return {
            "filename": filename,
            "size": file_size,
            "extension": ext
        }

    @classmethod
    def validate_text(cls, filename: str, text: str, run_id: str = None) -> Dict[str, Any]:
        """Tender gate for DOCX/TXT input (already converted to text); PDFs go through validate_file."""
        if not (text or "").strip():
            raise FileValidationError("Document has no extractable text.", run_id=run_id)
        is_tender, reason, _score = cls._score_tender_text(text[:60000].lower(), filename)
        if settings.TENDER_GATE_ENABLED and not is_tender:
            raise FileValidationError(
                f"Sorry, please upload a valid tender document. "
                f"The file '{filename}' was rejected because: {reason}.", run_id=run_id)
        log_pipeline_step("S1_FILE_VALIDATOR", status="SUCCESS", message=f"Validated text document {filename}")
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {"filename": filename, "size": len(text), "extension": ext}

    @classmethod
    def _is_tender_document(cls, doc: fitz.Document, filename: str = "") -> Tuple[bool, str, int]:
        """Scans the first 15 pages of a PDF with the tender heuristics. Returns (is_tender, reason, score)."""
        sample_text = ""
        max_pages = min(15, len(doc))
        for page_idx in range(max_pages):
            sample_text += " " + doc[page_idx].get_text().lower()
        has_images = any(doc[i].get_images() for i in range(max_pages))
        return cls._score_tender_text(sample_text, filename, max_pages, has_images)

    @classmethod
    def _score_tender_text(cls, sample_text: str, filename: str = "", pages_sampled: int = 0, has_images: bool = False) -> Tuple[bool, str, int]:
        """
        Explicit tender keywords and procurement signals weighed against non-tender terms
        (developer guides, system design books, payment gateway manuals...).
        """
        import re

        # If sample_text has negligible text (e.g. scanned image PDF; a portal stamp on each page adds a few chars)
        if len(sample_text.strip()) < 50 or (pages_sampled and has_images and len(sample_text.strip()) / pages_sampled < 150):
            fname = (filename or "").lower()
            if any(k in fname for k in ["tender", "rfp", "nit", "bid", "corrigendum", "addendum", "eoi", "rfq", "procurement"]):
                return True, "Scanned/image PDF document with tender filename (deferred to Stage 2b OCR)", 1
            return True, "Scanned PDF detected (deferred to Stage 2b OCR)", 1

        primary_tender_terms = [
            r"\btenders?\b", r"\brfp\b", r"\bgem\s+bid\b", r"\bbid\s+number\b", r"\be-procurement\b", r"\bbids?\s+(?:are\s+)?invited\b", r"\brequest for proposal\b", r"\bnotice inviting tender\b", r"\bnit\b",
            r"\bbid document\b", r"\bbidding document\b", r"\be-tender\b", r"\binvitation for bid\b",
            r"\binvitation for bids\b", r"\binvitation to bid\b", r"\bifb\b", r"\beoi\b", r"\bexpression of interest\b",
            r"\brfq\b", r"\brequest for quotation\b", r"\bcorrigendum\b", r"\baddendum\b", r"\bprocurement notice\b",
            r"\btender notice\b", r"\btender ref\b", r"\btender no\b", r"\btender id\b", r"\bpublic procurement\b",
            r"\beligibility criteria\b", r"\bpre-qualification\b", r"\bcommercial bid\b", r"\btechnical bid\b",
            r"\bearnest money deposit\b"
        ]

        secondary_tender_terms = [
            r"\bbidders?\b", r"\bbids?\b", r"\bearnest money\b", r"\bemd\b", r"\bbid security\b", r"\btender fee\b",
            r"\beligibility criteria\b", r"\bqualification criteria\b", r"\bpre-qualification\b",
            r"\btechnical criteria\b", r"\bfinancial criteria\b", r"\beligibility requirement\b",
            r"\bqualifying requirement\b", r"\blast date of submission\b", r"\bbid opening\b",
            r"\bissuing authority\b", r"\bsubmission deadline\b", r"\bscope of work\b"
        ]

        negative_signals = [
            # Resumes & CVs
            r"\bcurriculum vitae\b", r"\bresume\b", r"\bwork experience\b", r"\beducation background\b",
            # Invoices, Receipts & Bills
            r"\btax invoice\b", r"\binvoice no\b", r"\breceipt\b", r"\belectricity bill\b", r"\butility bill\b",
            r"\bsalary slip\b", r"\bpayslip\b", r"\bbank statement\b",
            # Developer guides & Technical books
            r"system design interview", r"system design fundamentals", r"developer guide", r"payment gateway",
            r"spring boot", r"installation guide", r"user manual", r"api reference", r"key fact statement",
            r"kfs", r"interview prep", r"codebase walkthrough", r"razorpay", r"billdesk", r"stripe",
            r"microservice architecture", r"tutorial", r"getting started", r"release notes",
            # Personal Identity Docs
            r"\baadhaar\b", r"\bpassport\b", r"\bvoter id\b", r"\bdriving license\b", r"\boffer letter\b",
            r"\brelieving letter\b", r"\brent agreement\b"
        ]

        weak_negatives = {r"\breceipt\b", r"\bresume\b", r"\bpassport\b", r"\baadhaar\b", r"\btax invoice\b", r"\binvoice no\b",
                          r"\bwork experience\b", r"\bpayslip\b", r"\bbank statement\b", r"\boffer letter\b", r"\bvoter id\b",
                          r"\bdriving license\b", r"\bgetting started\b", r"\brelease notes\b", r"\btutorial\b"}
        p_hits = [t for t in primary_tender_terms if re.search(t, sample_text)]
        s_hits = [t for t in secondary_tender_terms if re.search(t, sample_text)]
        n_hits = [t for t in negative_signals if re.search(t, sample_text)]

        # Tender evidence is weighed against non-tender evidence. A single stray keyword such as
        # "payment gateway" or "work experience" is normal inside a genuine tender and must not veto it.
        ml_hits = count_terms(sample_text, TENDER_TERMS)       # 'निविदा', 'ஒப்பந்தப்புள்ளி', 'టెండర్'... (Indian languages)
        evidence = (len(p_hits) * 5) + (len(s_hits) * 2) + (ml_hits * 5)
        counter_evidence = sum(2 if t in weak_negatives else 10 for t in n_hits)
        has_tender_structure = len(p_hits) >= 1 or len(s_hits) >= 3 or ml_hits >= 1

        # Rule 0: a document that names itself a tender-type document in its opening lines (title page) is one. Words such as
        # 'user manual' or 'receipt' further down (a list of deliverables, a payment clause) must not veto it.
        head = sample_text[:1500]
        title_terms = [r"\bexpression of interest\b", r"\brequest for (?:proposals?|quotations?)\b", r"\bnotice inviting\b",
                       r"\btender (?:document|notice)\b", r"\binvitation (?:for|to) bids?\b", r"\bbid(?:ding)? document\b",
                       r"\be-tender\b", r"\brfp\b", r"\brfq\b", r"\beoi\b", r"\bcorrigendum\b", r"\baddendum\b"]
        title_hits = [t for t in title_terms if re.search(t, head)]
        if title_hits and (len(p_hits) >= 2 or len(s_hits) >= 2):
            return True, (f"Valid Tender/RFP/EOI document (named in its title; primary signals={len(p_hits)}, "
                          f"secondary signals={len(s_hits)}, non-tender signals={len(n_hits)})"), evidence

        # Rule 1: negative keywords and no real tender structure -> clearly some other kind of document
        if n_hits and not has_tender_structure:
            matched_term = n_hits[0].replace(r"\b", "")
            return False, f"Document recognized as non-tender file (matched '{matched_term}')", 0

        # Rule 2: require at least ONE primary tender term OR at least 2 secondary procurement signals
        if len(p_hits) == 0 and len(s_hits) < 2 and ml_hits == 0:
            return False, "Document lacks mandatory Tender/RFP headers (such as 'Tender', 'RFP', 'Notice Inviting Tender', 'Bid Document', 'EOI')", 0

        # Rule 3: tender signals must outweigh the non-tender ones
        if has_tender_structure and evidence >= counter_evidence:
            return True, (f"Valid Tender/RFP document (primary signals={len(p_hits)}, "
                          f"secondary signals={len(s_hits)}, non-tender signals={len(n_hits)})"), evidence

        matched = ", ".join(t.replace(r"\b", "") for t in n_hits[:3])
        return False, (f"Document has more non-tender than tender signals (matched {matched}); "
                       "it does not look like a tender document"), evidence

    @classmethod
    def merge_files_if_needed(cls, files: List[Tuple[str, bytes]], run_id: str = None) -> bytes:
        """
        If two files uploaded (e.g. tender PDF + amendment), merge them into a single PDF document.
        """
        if not files:
            raise FileValidationError("No files provided for validation.", run_id=run_id)

        if len(files) == 1:
            cls.validate_file(files[0][0], files[0][1], run_id=run_id)
            return files[0][1]

        # Merge PDFs
        main_doc = None
        for filename, content in files:
            cls.validate_file(filename, content, run_id=run_id)
            doc = fitz.open(stream=content, filetype="pdf" if filename.lower().endswith(".pdf") else "docx")
            if main_doc is None:
                main_doc = fitz.open()
                main_doc.insert_pdf(doc)
            else:
                main_doc.insert_pdf(doc)
            doc.close()

        merged_bytes = main_doc.write()
        main_doc.close()
        log_pipeline_step("S1_FILE_VALIDATOR", status="SUCCESS", message=f"Merged {len(files)} files successfully")
        return merged_bytes
