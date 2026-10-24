# ZYNEX Tender Analysis Engine: End-to-End Technical Architecture & Database Specification

This document provides a comprehensive technical breakdown of the Tender Analysis module in ZYNEX (**Z**ero-Cloud, **Y**our-Data, **N**eural **E**stimation & e**X**ecution). It details the complete lifecycle from document ingestion through the multi-stage parsing, heuristic filtering, neural criteria extraction, deterministic rule engine evaluation, database schema architecture, and history persistence.

---

## 1. High-Level Architectural Flow

When a user submits a tender document via the frontend web interface, the platform initiates a hybrid deterministic-neural pipeline. The system enforces zero-data-leakage constraints: parsing, optical character recognition (OCR), vector operations, and neural extractions execute entirely on local hardware.

```mermaid
flowchart TD
    subgraph INGESTION["1. Ingestion & Pre-Validation"]
        Upload["Client POST /tender/upload"] --> GateCheck["Extension & Size Checks"]
        GateCheck --> FastGate["S1: Fast Pre-Validation Gate"]
        FastGate --> DiskSave["Write binary to UPLOAD_DIR/{uuid}.ext"]
        DiskSave --> DBPersistDoc["Insert Document Record (DB)"]
        DBPersistDoc --> DBPersistReport["Insert EligibilityReport (PENDING)"]
        DBPersistReport --> SpawnTask["asyncio.create_task(_run_pipeline)"]
    end

    subgraph PIPELINE["2. Staged Processing Pipeline (S1-S10)"]
        SpawnTask --> S1["S1: File & Heuristic Tender Validation"]
        S1 --> S2A["S2a: PDF Layout & Table Extraction (PyMuPDF)"]
        S2A --> S2B{"Has Scanned Pages?"}
        S2B -- Yes --> OCR["S2b: Tesseract OCR Engine (~216 DPI)"]
        S2B -- No --> S3["S3: Hierarchy & Structure Analyzer"]
        OCR --> S3
        S3 --> S4["S4: Physical Page & Clause Chunker"]
        S4 --> S5["S5: Deterministic Section Locator & Prefilter"]
        S5 --> S6["S6: Neural Criteria Extraction (Local Ollama)"]
        S6 --> S7["S7: Fuzzy Grounding & Evidence Verification"]
        S7 --> S8["S8: Company Data Alignment (entity, canonical value, domain match)"]
        S8 --> S9["S9: Company Master Audit (Rule Engine)"]
        S9 --> S10["S10: Verdict Computation & Audit Explanations"]
    end

    subgraph PERSISTENCE["3. State & History Persistence"]
        S10 --> UpdateReport["Update EligibilityReport (status, criteria, matrix)"]
        UpdateReport --> CommitDB["PostgreSQL Transaction Commit"]
        CommitDB --> PollStream["Client Polling (/status & /progress) -> Done"]
    end
```

---

## 2. Ingestion & Storage Lifecycle

### 2.1 File Storage on Disk
* **Physical Location**: Uploaded files do **not** get stored as raw BLOBs in the PostgreSQL database to preserve database memory and avoid I/O bottlenecks. Instead, they are written to the directory specified by `UPLOAD_DIR` in `backend/.env` (default: `./uploads` or `/var/lib/zynex/uploads`).
* **Isolation & Collision Safety**: The file is stored using a UUID v4 string:
  $$\text{filepath} = \text{UPLOAD\_DIR} + "/" + \text{UUID4()} + \text{ext}$$
* **Permissions**: Filesystem read/write operations belong strictly to the application runtime service user, ensuring isolation from unprivileged OS accounts.

### 2.2 Database Initialization
During the upload transaction in [`upload_tender`](file:///home/xenovex/xos-tender-engine/backend/app/api/v1/tender.py#L124-L165):
1. **`documents` Table Record**:
   - `original_filename`: Retains original file name (e.g., `NIT_Transport_2026.pdf`).
   - `filename`: Stores disk basename (e.g., `a7c1b128-4e12-4c2f-b4d2-d8b8e64c23f1.pdf`).
   - `file_path`: Absolute path on the server filesystem.
   - `doc_type`: Set to `DocumentType.TENDER`.
   - `status`: Set to `DocumentStatus.ANALYZED`.
   - `uploaded_by`: Extracted from the authenticated user's JWT payload (`sub`).
2. **`eligibility_reports` Table Record**:
   - Replaces any previous report associated with this document ID.
   - `status`: Initialized to `EligibilityStatus.PENDING`.
   - `compliance_matrix`: Initialized to `{"state": "RUNNING", "run": run_info(options)}`.
   - `summary`: Initialized to `"Analysis in progress…"`.

### 2.3 Live Progress & Event Streaming
To prevent blocking HTTP worker threads, execution is dispatched to the event loop using `asyncio.create_task(_run_pipeline(...))`:
- A global dictionary `_TASKS[report_id]` holds a strong reference to the background task, enabling graceful task cancellation via `POST /tender/{run_id}/cancel`.
- An in-memory queue (`progress_store`) keys messages by `_elig_key(doc_id) = "elig_{doc_id}"`.
- The frontend UI periodically polls `GET /tender/{run_id}/status` and `GET /eligibility/{doc_id}/progress`, retrieving real-time log messages, current stage identifiers, and execution metrics.

---

## 3. Deep Dive into Pipeline Stages (S1 to S10)

The core analysis pipeline is orchestrated by [`EligibilityPipeline`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/pipeline.py#L59-L215).

```
+----+-----------------------------+------------------------------------+---------------------------------------+
| St | Stage Name                  | Primary Module                     | Processing Nature                     |
+----+-----------------------------+------------------------------------+---------------------------------------+
| S1 | File & Tender Gate          | file_validator.py                  | Deterministic / Regex Heuristics      |
| S2 | Layout Extraction & OCR     | pdf_extractor.py, ocr_service.py   | PyMuPDF C-Bindings & Tesseract OCR   |
| S3 | Document Hierarchy          | structure_analyzer.py              | Deterministic Structural Parsing      |
| S4 | Clause Segmentation         | chunker.py                         | Page-Context Line Chunker             |
| S5 | Section Locator & Prefilter | locator.py, prefilter.py           | Vocabulary / Table-Window Scoring     |
| S6 | Criteria Extraction         | criteria_extractor.py, llm_call.py | Local Neural Inference (Ollama/NVIDIA)|
| S7 | Grounding & Evidence Check  | post_validator.py                  | RapidFuzz Partial Ratio Matching      |
| S8 | Company Data Alignment      | company_alignment.py, domain_vocab.py, normalizer.py | Entity mapping, canonical values, domain matching |
| S9 | Company Master Audit        | rule_engine.py, company_facts.py   | Deterministic Relational Rule Engine  |
| S10| Verdict & Audit Reasoning   | verdict.py, reasoning.py           | Aggregation & Deterministic Fallbacks |
+----+-----------------------------+------------------------------------+---------------------------------------+
```

---

### Stage S1: File & Document Heuristic Validation
* **Source Module**: [`app.services.eligibility.file_validator`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/file_validator.py#L10-L100)
* **Goal**: Validate file integrity and prevent non-tender documents (resumes, invoices, technical books, source code) from reaching costly extraction stages.
* **Mechanism**:
  1. **Extension & Size Gate**: Restricts uploads to `.pdf` (and text), enforcing limits ($1\text{ KB} \le \text{Size} \le \text{MAX\_UPLOAD\_SIZE\_MB}$).
  2. **Encryption Check**: Detects password protection using `fitz.Document.is_encrypted`.
  3. **Tender Gating Heuristics** (`_score_tender_text`): Samples up to the first 15 pages:
     - **Primary Procurement Terms** (weight +5): `\btenders?\b`, `\brfp\b`, `\be-procurement\b`, `\bnotice inviting tender\b`, `\bearnest money deposit\b`, etc.
     - **Secondary Signals** (weight +2): `\bbidders?\b`, `\bemd\b`, `\btender fee\b`, `\bqualification criteria\b`, etc.
     - **Negative Signals** (penalty -10): Resumes (`curriculum vitae`), invoices (`tax invoice`, `electricity bill`), developer guides (`system design interview`, `spring boot`, `payment gateway`), ID documents (`aadhaar`, `passport`).
  4. Documents failing to clear the heuristic threshold trigger a `FileValidationError` returning:
     `"Sorry, please upload a valid tender document. The file '...' was rejected because: ..."`
* **Database Access**: None. Purely CPU-bound memory and file validation.

---

### Stage S2: Layout Extraction (S2a) & Scanned Page OCR (S2b)
* **Source Modules**:
  - S2a: [`app.services.eligibility.pdf_extractor`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/pdf_extractor.py#L8-L100)
  - S2b: [`app.services.eligibility.ocr_service`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/ocr_service.py#L11-L60)
* **Mechanism**:
  1. **Layout & Table Extraction (S2a)**:
     - Reads raw PDF structures using PyMuPDF (`fitz`).
     - Detects ruled vector drawings (`page.get_cdrawings() >= 4`) and extracts multi-row, multi-column tables using `page.find_tables()`.
     - Formats tabular data into clean pipe-delimited Markdown tables bounded by `[TABLE START]` and `[TABLE END]` tags.
     - Strips repeating running headers, footers, tender references, and pagination across pages via coordinate analysis.
  2. **Scanned Page Detection & Tesseract OCR (S2b)**:
     - Identifies scanned or image-heavy pages where vector text is missing but image coverage exceeds threshold (`_image_cover`).
     - Rasterizes page to PNG at high fidelity (`RENDER_SCALE = 3`, $\approx 216\text{ DPI}$).
     - Invokes local `pytesseract.image_to_string` to recover text, converting blocks into paragraph objects.
* **Database Access**: None.

---

### Stage S3: Hierarchy & Document Structure Analyzer
* **Source Module**: [`app.services.eligibility.structure_analyzer`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/structure_analyzer.py#L5-L100)
* **Goal**: Reconstruct semantic document hierarchy and eliminate cross-page table fragmentation.
* **Mechanism**:
  - Classifies text blocks into structural nodes: `chapter`, `section`, `clause`, `table`, or `paragraph`.
  - Employs regex patterns for numbered chapters (e.g., `SECTION II`, `ANNEXURE-A`), numbered sections (`2. QUALIFICATION REQUIREMENTS`), and sub-clauses (`3.1.2`, `1(a)`, `(i)`).
  - Merges split table rows and multi-page continuation tables into singular semantic blocks.
* **Database Access**: None.

---

### Stage S4: Physical Page & Clause Segmentation (Chunker)
* **Source Module**: [`app.services.eligibility.chunker`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/chunker.py#L6-L65)
* **Goal**: Prevent micro-fragmentation. Generates coherent, bounded chunks formatted for the LLM context window.
* **Mechanism**:
  - Groups nodes by physical page number.
  - Constructs `ChunkSchema` models with predictable IDs:
    $$\text{chunk\_id} = \text{"ck\_"} + \text{run\_id[:8]} + \text{"\_"} + \text{page\_no:03d} + \text{"\_"} + \text{seq:03d}$$
  - Preserves hierarchical metadata: `chapter`, `section`, `clause`, `physical_page`, `content_type`, and `char_count`.
* **Database Access**: None.

---

### Stage S5: Deterministic Section Locator & Vocabulary Pre-Filter
* **Source Modules**:
  - Locator: [`app.services.eligibility.locator`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/locator.py#L1-L60)
  - Pre-filter: [`app.services.eligibility.prefilter`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/prefilter.py#L1-L60)
* **Goal**: Minimize LLM latency and compute load on CPU/edge servers.
* **Mechanism**:
  1. **Section Locator (`find_core_chunks`)**:
     - Scans headings for explicit pre-qualification anchors (`"Pre-Qualification Criteria"`, `"Eligibility Conditions"`, `"Minimum Qualifying Criteria"`).
     - Follows continuation tables and prose across consecutive pages (up to `MAX_CORE_PAGES = 12`).
  2. **Vocabulary Pre-filter (`select_chunks`)**:
     - For large tenders where an explicit section anchor is missing, chunks are scored against procurement vocabulary (`turnover`, `net worth`, `solvency`, `blacklist`, `similar work`, `iso`, `cmmi`, `emd`).
     - Chunks scoring above `STRONG_SCORE = 6` pull their adjacent neighbour pages to preserve multi-page clause context.
     - Unrelated boilerplate pages (dispute arbitration, general contract conditions, sample bank guarantee forms) are filtered out.
* **Database Access**: None.

---

### Stage S6: Neural Criteria Extraction
* **Source Modules**:
  - Extractor: [`app.ai.tender.criteria_extractor`](file:///home/xenovex/xos-tender-engine/backend/app/ai/tender/criteria_extractor.py#L1-L100)
  - Caller: [`app.ai.tender.llm_call`](file:///home/xenovex/xos-tender-engine/backend/app/ai/tender/llm_call.py)
  - Client: [`app.ai.llm_client`](file:///home/xenovex/xos-tender-engine/backend/app/ai/llm_client.py)
* **Goal**: Extract structured, machine-evaluable eligibility criteria from text and tables.
* **Mechanism**:
  - Dispatches chunks to the local Ollama instance (or configured NVIDIA provider) with controlled concurrency (`settings.LLM_CONCURRENCY`, default 2).
  - Uses two specialized prompts depending on chunk type:
    - **Tabular Rows**: `build_table_user_prompt` batches up to 8 table rows per prompt, enforcing strict extraction of serial numbers, criteria, required values, and proof documents.
    - **Narrative Clauses**: `build_extraction_user_prompt` processes narrative prose clauses.
  - Enforces JSON Schema constraints with retry on malformed JSON (`json_parse.parse_json_robust`).
  - Maps requirements to the **45-field procurement ontology** (e.g., `annual_turnover`, `net_worth`, `similar_work_value`, `iso_9001`, `cmmi_level`).
  - Extracts exact verbatim quotes (`source_text`) for auditability.
* **Database Access**: None directly; models read provider configuration from `settings`.

---

### Stage S7: Fuzzy Grounding & Evidence Check
* **Source Module**: [`app.services.eligibility.post_validator`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/post_validator.py#L48-L100)
* **Goal**: Eliminate AI hallucinations and ungrounded statements.
* **Mechanism**:
  - Compares the LLM's returned `source_text` quote against the actual chunk text.
  - Normalizes text with Unicode NFKC, folding whitespace and dashes.
  - Computes fuzzy partial ratio using `rapidfuzz.fuzz.partial_ratio`:
    $$\text{score} = \text{partial\_ratio}(\text{normalized\_quote}, \text{normalized\_chunk})$$
  - If $\text{score} \ge \text{GROUNDING\_FUZZY\_THRESHOLD}$ (default 92%), `exact_match = True`.
  - If below threshold, the criterion is **not** discarded; it is flagged with `exact_match = False` and routed to `NEEDS_REVIEW` to ensure human auditors review it.
  - Deduplicates repeated criteria based on `(field, operator, value)`.
* **Database Access**: None.

---

### Stage S8: Canonical Normalizer
* **Source Module**: [`app.services.eligibility.normalizer`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/normalizer.py#L5-L70)
* **Goal**: Standardize heterogeneous tender expressions into comparable types.
* **Mechanism**:
  - **Currency & Units**: Converts Indian financial units into standard numerical floats:
    - `5.5 Crore` $\to 55,000,000.0$
    - `75 Lakhs` $\to 7,500,000.0$
    - `10 Million` $\to 10,000,000.0$
    - `₹` / `INR` / `Rs.` standardizations.
  - **Words to Numbers**: Parses prose numerals (`"three years"` $\to 3$).
  - **Fiscal Years**: Extracts Indian fiscal year ranges (`FY 2023-24` $\to 2024$).
  - **Certifications**: Standardizes names (e.g., `"ISO-9001:2015"` $\to `"iso_9001"`).
* **Database Access**: None.

---

### Stage S9: Company Master Audit (Rule Engine)
* **Source Modules**:
  - Engine: [`app.services.eligibility.rule_engine`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/rule_engine.py#L1-L60)
  - Facts Provider: [`app.services.eligibility.company_facts`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/company_facts.py#L69-L94)
* **Goal**: Compare extracted criteria against actual company records. Never guess or fabricate data.
* **Mechanism**:
  - Loads actual company data via [`CompanyFactsProvider.load(db)`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/company_facts.py#L69-L94):
    1. `financial_records` $\to$ Turnover by fiscal year (`turnover_by_fy`).
    2. `certifications` $\to$ Certificate validity dates and status (`certifications`).
    3. `employees` $\to$ Active headcount and employee skill catalog.
    4. `projects` $\to$ Past completed projects, values, and technology stacks.
    5. `technologies` $\to$ Master technology competency database.
  - Evaluates each criterion against facts:
    - **`PASS`**: Company metric strictly satisfies threshold.
    - **`FAIL`**: Company record exists but falls below threshold, or certificate is expired.
    - **`MISSING`**: The knowledge base contains no record for this attribute (e.g., unrecorded ISO certification or net worth). Never fabricated as Pass.
    - **`NEEDS_REVIEW`**: Ambiguous requirement or ungrounded quote.
    - **`INFORMATIONAL`**: Procedural parameters (EMD amount, submission dates, portal instructions).
* **Database Access**:
  - **Read Queries** across `financial_records`, `certifications`, `employees`, `projects`, and `technologies`.

---

### Stage S10: Verdict Computation & Audit Reasoning
* **Source Modules**:
  - Aggregator: [`app.services.eligibility.verdict`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/verdict.py#L24-L85)
  - Reasoning: [`app.services.eligibility.reasoning`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/reasoning.py#L1-L32)
* **Goal**: Synthesize final bid/no-bid decision and compile audit explanations.
* **Verdict Decision Logic**:
  $$\text{Verdict} = \begin{cases} 
  \mathbf{NOT\_ELIGIBLE} & \text{if any mandatory criterion has status } \mathbf{FAIL} \\
  \mathbf{PARTIAL} & \text{if any mandatory criterion has status } \mathbf{MISSING} \text{ or } \mathbf{NEEDS\_REVIEW} \\
  \mathbf{ELIGIBLE} & \text{if all mandatory criteria have status } \mathbf{PASS} \\
  \mathbf{PENDING} & \text{if zero mandatory criteria were found}
  \end{cases}$$
* **Safety Net for Incomplete Extractions**:
  If neural extraction failed on any chunk (`chunks_failed > 0`), the pipeline refuses to award an `ELIGIBLE` status; it downgrades the verdict to `PARTIAL` and appends a clear warning to prevent missed requirements.
* **Audit Explanations**:
  - Generates deterministic, auditable evidence strings for every item.
  - For outright failures, optionally prompts the LLM to draft human-readable audit explanations.
* **Database Access**: Updates `eligibility_reports` table (see Section 4).

---

## 4. Database Infrastructure, Schemas & Table Inventory

### 4.1 Host & Connection Configuration

The application database runs locally on PostgreSQL:
* **Host**: `localhost` (127.0.0.1)
* **Port**: `5432`
* **Target Database**: **`zynex`**
* **User**: `zynex`
* **Password**: `zynex`
* **Async Connection URI**: `postgresql+asyncpg://zynex:zynex@localhost:5432/zynex`
* **Sync Migration URI**: `postgresql://zynex:zynex@localhost:5432/zynex`
* **Current Migration Revision**: `b4bdf9f43063` (Managed by Alembic)

---

### 4.2 Database Disambiguation (`zynex` vs. `xenovex_tender_db`)

On PostgreSQL server `localhost:5432`, multiple databases coexist. When viewing tables through database GUIs (such as DBeaver, pgAdmin, Navicat, or VS Code), users frequently encounter tables from an older ASP.NET Core project:

```
+----------------------------------------------------------------------------------------------------+
| PostgreSQL Host: localhost:5432                                                                    |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [xenovex_tender_db]  (36 Tables - Legacy C# / ASP.NET Core / EF Core Project)                     |
|  - AspNetUsers, AspNetUserClaims, AspNetRoles, __EFMigrationsHistory                               |
|  - Company, CompanyCapability, CompanyPersonnel, TenderRequirement, RequirementEvaluation        |
|                                                                                                    |
|  [zynex]  (22 Tables - ACTIVE ZYNEX Python / FastAPI Engine)                                       |
|  - documents, tender_chunks, eligibility_reports                                                   |
|  - clients, projects, employees, technologies, certifications, financial_records                   |
|  - cost_parameters, cost_sheets, estimation_*, proposals, users, roles, app_settings               |
+----------------------------------------------------------------------------------------------------+
```

#### How to Switch Your GUI Tool to the Correct Database:
1. In **DBeaver** / **pgAdmin** / **TablePlus**:
   - Right-click the connection $\to$ **Edit Connection** (or **Connection Properties**).
   - Change the **Database name** from `xenovex_tender_db` (or `postgres`) to **`zynex`**.
   - Ensure Username is `zynex` and Password is `zynex`.
   - Click **Save / Reconnect**.
2. Expand `zynex` $\to$ **Schemas** $\to$ **public** $\to$ **Tables**. All 22 ZYNEX platform tables will be displayed.

---

### 4.3 Complete 22-Table Inventory in `zynex` Database

The `zynex` database contains exactly **22 tables**, organized into 6 functional clusters:

```mermaid
erDiagram
    %% Cluster 1: Ingestion & Document Storage
    documents ||--o{ tender_chunks : "chunked_into"
    documents ||--o{ eligibility_reports : "evaluated_in"
    documents ||--o{ estimation_reports : "estimated_in"
    documents ||--o{ proposals : "generates"

    %% Cluster 2: Knowledge Base
    clients ||--o{ projects : "contracts"
    projects ||--o{ project_documents : "attaches"
    project_documents ||--o{ project_document_chunks : "chunks"

    %% Cluster 3: Governance & RBAC
    users ||--o{ documents : "uploads"
    users ||--o{ app_settings : "manages"
    roles ||--o{ users : "assigns"

    %% Cluster 4: Cost Estimation
    estimation_projects ||--o{ estimation_features : "contains"
    estimation_projects ||--o{ estimation_resources : "allocates"
    estimation_projects ||--o{ cost_sheets : "prices"
    estimation_projects ||--o{ estimation_reports : "exports"
```

#### Table Specifications & Current Seed State

| # | Table Name | Primary Key | Foreign Keys | Functional Purpose | Live Row Count | Seed Status |
|---|---|---|---|---|---|---|
| **1** | `alembic_version` | `version_num` | None | Migration tracker (`b4bdf9f43063`) | 1 | Head revision applied |
| **2** | `app_settings` | `key` | `updated_by -> users.id` | Live runtime config (`ai.default_model`) | 1 | Seeded (`qwen2.5:14b`) |
| **3** | `roles` | `id` | None | RBAC definitions (`admin`, `bid_manager`, `viewer`) | 3 | Seeded via `init-roles` |
| **4** | `users` | `id` | `role_id -> roles.id` | Authenticated operators and administrators | 2 | Seeded (`AdminPassword123!`) |
| **5** | `clients` | `id` | None | Enterprise clients (past & active contracts) | 6 | Seeded via `seed_demo_data` |
| **6** | `technologies` | `id` | None | Catalog of technical capabilities & stacks | 24 | Seeded via `seed_demo_data` |
| **7** | `certifications` | `id` | None | Company certificates (ISO 9001, ISO 27001, etc.) | 6 | Seeded via `seed_demo_data` |
| **8** | `employees` | `id` | None | Personnel directory (roles, skills, rates) | 12 | Seeded via `seed_demo_data` |
| **9** | `projects` | `id` | `client_id -> clients.id` | Prior project track record for experience audit | 7 | Seeded via `seed_demo_data` |
| **10** | `financial_records`| `id` | None | Annual turnover, net worth, net profit per FY | 0 | Populated per fiscal audit |
| **11** | `cost_parameters` | `id` | None | Estimation coefficients (margin, contingency) | 10 | Seeded via `seed_cost_parameters` |
| **12** | `cost_sheets` | `id` | `estimation_project_id` | Calculated Bill of Quantities (BOQ) | 0 | Generated on estimation |
| **13** | `documents` | `id` | `uploaded_by -> users.id`| Master records of uploaded tender/SRS files | 5 | Seeded sample tenders |
| **14** | `tender_chunks` | `id` | `document_id -> documents.id` | Semantic document chunks + embeddings | 0 | Dynamically populated during RAG |
| **15** | `eligibility_reports`| `id` | `document_id -> documents.id`| Completed tender compliance runs & audit trails| 5 | Seeded evaluation reports |
| **16** | `estimation_projects`| `id`| `document_id -> documents.id`| Active software/tender estimation workspaces | 0 | Created on estimation run |
| **17** | `estimation_features`| `id`| `estimation_project_id` | Extracted functional feature breakdown | 0 | Created on estimation run |
| **18** | `estimation_resources`| `id`| `estimation_project_id`| Resource role allocation for cost modeling | 0 | Created on estimation run |
| **19** | `estimation_reports`| `id` | `document_id -> documents.id`| Exported final estimation calculations | 0 | Created on estimation run |
| **20** | `proposals` | `id` | `document_id`, `eligibility_report_id` | Generated technical and commercial bid proposals | 0 | Created on proposal export |
| **21** | `project_documents`| `id` | `project_id -> projects.id` | Reference documentation attached to projects | 0 | Created per project archive |
| **22** | `project_document_chunks`| `id` | `project_document_id` | Chunks & vectors for past project retrieval | 0 | Created on project indexing |

---

### 4.4 Architectural Rationale: Why the Schema is Initialized This Way

1. **Decoupled File Storage (`documents` vs. Disk)**:
   - File binaries are kept on disk (`./uploads`), while metadata lives in `documents`.
   - Storing large 50 MB PDFs inside PostgreSQL `BYTEA` columns creates bloat, degrades buffer hit rates, and slows down database backups.
2. **Denormalized Audit Trails (`eligibility_reports.compliance_matrix["stages"]`)**:
   - Rather than creating 10 separate relational tables for S1 through S10 intermediate outputs, ZYNEX stores each step's execution output as a structured JSON artifact inside `compliance_matrix["stages"]`.
   - This prevents complex multi-table joins on historical queries and allows instant playback of stages in the frontend Stage Inspector.
3. **Isolated Enterprise Knowledge Base (The Ground Truth for Stage 9)**:
   - The tables `financial_records`, `certifications`, `employees`, `projects`, and `technologies` represent corporate facts.
   - The deterministic Rule Engine queries these tables directly rather than asking the LLM to "hallucinate" whether the company has an ISO certificate.
4. **Downstream Pipeline Continuity**:
   - A single uploaded tender (`documents.id`) cascades downstream:
     - Stage 1: `eligibility_reports` determines if the company can bid.
     - Stage 2: `estimation_projects` breaks down features and estimates effort/cost using `cost_parameters`.
     - Stage 3: `proposals` drafts the final bid submission referencing both the eligibility matrix and the cost sheet.

---

## 5. History & Lifecycle Management

### 5.1 Querying Tender History
When an operator navigates to the History tab in the web application, the frontend calls `GET /api/v1/tender/history`:

```sql
-- Query executed during history view:
SELECT 
    er.id AS run_id,
    er.document_id,
    er.status,
    er.criteria,
    er.compliance_matrix,
    er.summary,
    er.created_at,
    d.original_filename,
    d.file_path,
    d.uploaded_by,
    u.email AS uploader_email
FROM eligibility_reports er
JOIN documents d ON er.document_id = d.id
LEFT JOIN users u ON d.uploaded_by = u.id
ORDER BY er.id DESC;
```

#### State Mapping:
The API maps internal database status tokens to standardized frontend states:
- `RUNNING` $\to$ `processing`
- `DONE` $\to$ `completed`
- `FAILED` $\to$ `failed`
- `CANCELLED` $\to$ `cancelled`

---

### 5.2 Intermediate Stage Artifacts (JSON Inspector)
The endpoint `GET /api/v1/tender/{run_id}/stages` provides complete transparency. Every step recorded by `EligibilityPipeline._record(stage_id, step, output)` is read directly from `eligibility_reports.compliance_matrix["stages"]`. Auditors can inspect:
- `S1`: File validation metrics and heuristic gate scores.
- `S2A`: PyMuPDF layout and detected table bounding boxes.
- `S2B`: Tesseract OCR logs, character counts, and unreadable page alerts.
- `S3`: Detected chapter, section, and clause hierarchy tree.
- `S4`: Chunk breakdown and physical page mapping.
- `S6`: Raw neural extraction outputs directly from the model.
- `S7`: Fuzzy grounding match ratios, near-miss scores, and deduplications.
- `S9`: Relational evaluation results matched against company records.
- `S10`: Final mathematical verdict calculation.

---

### 5.3 PDF Audit Report Generation
Users can download an official proposal-ready PDF via `GET /api/v1/tender/{run_id}/report/pdf`:
- Generated deterministically by [`app.services.eligibility.report_pdf`](file:///home/xenovex/xos-tender-engine/backend/app/services/eligibility/report_pdf.py).
- Uses WeasyPrint to produce a styled multi-page compliance report containing:
  - Executive summary and audit statistics.
  - Color-coded compliance matrix table (Pass / Fail / Missing / Needs Review).
  - Exact source quotes and page numbers for tender citations.
  - Required submission action checklist.

---

### 5.4 Deletion & Reference-Counted Cleanup
When an analysis is deleted via `DELETE /api/v1/tender/{run_id}`:
1. Deletes the `EligibilityReport` record from PostgreSQL.
2. Clears live progress buffers from `progress_store`.
3. Performs reference counting: checks if the underlying `Document` is referenced by `EstimationReport`, `Proposal`, or `EstimationProject`.
4. If no other modules are using the document:
   - Removes physical file from server disk (`os.remove(doc.file_path)`).
   - Cascades deletion of `tender_chunks`.
   - Deletes the `Document` record.

---

## 6. End-to-End Execution Trace Matrix

| Step | Component / Function | Input | Output / State | DB Access & Tables |
|---|---|---|---|---|
| **0. Upload** | `POST /tender/upload` | Multipart File, Form Options | File on disk (`uploads/`), `doc_id`, `report_id` | `INSERT documents`, `INSERT eligibility_reports` |
| **S1. Gate** | `FileValidator.validate_file` | PDF Binary stream | Pass / Fail; heuristic score | None (CPU regex) |
| **S2a. Extract** | `PDFExtractor.extract_pdf_data` | PDF Binary stream | Pages, layout blocks, Markdown tables | None |
| **S2b. OCR** | `OCRService.process_scanned_page` | Scanned Page PNG ($216\text{ DPI}$) | OCR text blocks via Tesseract | None |
| **S3. Structure**| `StructureAnalyzer.analyze_structure` | Page block streams | Hierarchical document node tree | None |
| **S4. Chunk** | `Chunker.create_chunks` | Document node tree | Array of `ChunkSchema` objects | None |
| **S5. Locate** | `find_core_chunks` & `select_chunks` | Chunks array | Prioritized candidate chunk IDs | None |
| **S6. AI Extract**| `CriteriaExtractor.extract` | Prioritized candidate chunks | Array of raw `CriterionSchema` | Local Ollama / NVIDIA API calls |
| **S7. Grounding**| `PostValidator.validate_and_deduplicate` | Raw criteria + Chunks | Verified, deduplicated criteria | None |
| **S8. Normalize**| `Normalizer.normalize_criteria` | Criteria values & units | Standardized floats, ISO dates, enums | None |
| **S9. Master Audit**| `RuleEngine.evaluate` | Criteria + `CompanyFacts` | Evaluated `CriterionResultSchema` | `SELECT` from `financial_records`, `certifications`, `employees`, `projects`, `technologies` |
| **S10. Verdict** | `VerdictAggregator.aggregate` | Evaluated criteria array | Overall verdict (`PASS`/`FAIL`/`PARTIAL`) | `UPDATE eligibility_reports` |
| **Finish** | `_run_pipeline` finalization | Final report dict | State set to `DONE` | `COMMIT` to PostgreSQL (`eligibility_reports`) |
| **History View** | `GET /api/v1/tender/history` | User session token | Array of past tender runs + metrics | `SELECT eligibility_reports JOIN documents JOIN users` |
| **Stage Inspect** | `GET /api/v1/tender/{id}/stages` | Run ID | JSON dictionary of S1–S10 stage payloads | `SELECT eligibility_reports.compliance_matrix` |
