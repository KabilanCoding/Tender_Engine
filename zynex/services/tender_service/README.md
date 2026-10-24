# ZYNEX Tender Analysis Microservice (`tender-service`)

A dedicated microservice extracted from the ZYNEX platform. It manages:
- **Tender Ingestion & Heuristic Gating** (PDF / Scanned pages)
- **High-Fidelity OCR & Layout Parsing** (PyMuPDF, Tesseract OCR)
- **10-Stage Evaluation Pipeline (S1-S10)**:
  - S1: Heuristic File & Keyword Validation
  - S2: Layout Extraction & Scanned Page OCR
  - S3: Document Hierarchy & Chapter Structure
  - S4: Physical Page Chunker
  - S5: Section Locator & Procurement Vocabulary Pre-filter
  - S6: Neural Criteria Extraction (via local Ollama)
  - S7: Fuzzy Citation Grounding (RapidFuzz)
  - S8: Canonical Normalization (Crores/Lakhs/USD/Dates)
  - S9: Company Master Facts Audit (Deterministic Relational Evaluation)
  - S10: Verdict Synthesis & Audit Reasoning
- **Proposal-Ready PDF Export** (WeasyPrint)
- **Tender Tiger Integration** (Scraped procurement notices & file inspector)

---

## Service Endpoints

* **Base URL**: `http://localhost:8001`
* **Health Check**: `GET /health`
* **Readiness Check**: `GET /health/ready`
* **API Documentation**: `http://localhost:8001/docs`

### Primary Routes
* `POST /api/v1/tender/upload` - Ingest and start background analysis
* `GET  /api/v1/tender/history` - List past evaluation runs
* `GET  /api/v1/tender/{run_id}/status` - Live execution progress
* `GET  /api/v1/tender/{run_id}/report` - Final evaluation verdict & criteria
* `GET  /api/v1/tender/{run_id}/stages` - S1–S10 intermediate stage inspector
* `GET  /api/v1/tender/{run_id}/report/pdf` - Download compliance PDF
* `GET  /api/v1/tender-tiger/tenders` - Query scraped tender notices
* `GET  /api/v1/tender-tiger/organizations` - Filter by buyer organization
* `POST /api/v1/tender-tiger/files/{file_id}/analyse` - Launch analysis on scraped file

---

## Running Standalone

```bash
# 1. Activate virtual environment
source ../../backend/.venv/bin/activate

# 2. Run with uvicorn
uvicorn main:app --reload --port 8001
```


---

## One copy of the pipeline

The service does **not** keep its own copy of the analysis code. `app/ai`, `app/core`, `app/models`, `app/schemas`, `app/parsers`,
`app/services` and the `tender`, `tender_tiger`, `eligibility` and `progress_store` routes are symbolic links to `backend/app/...`.
Only `main.py` and `app/api/v1/router.py` belong to the service. A fix to the rule engine, the company-data comparison or the
prompts is therefore made once and is live in both services (`./run` restarts the service when `backend/app` changes).
(Before this, the service held an older copy and tender runs on port 8001 did not use the newer comparison rules.)
