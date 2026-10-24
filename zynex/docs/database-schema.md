# ZYNEX database schema: current state, target design and why

Status: **proposal, nothing in this document has been applied to the database yet.**
Database: PostgreSQL 16 (`zynex`). Written from the live schema and data on 2026-10-12.

How to read this document: section 1 is the current ("old") schema, section 2 lists what is wrong with it,
section 3 is the target ("new") schema, section 4 is the change list with the reason for every change, and
section 5 is how to get there safely.

---

## 1. Current schema (old)

25 tables in `public`, grouped by what they do. Row counts are from the live database.

### 1.1 Platform
| Table | Rows | Columns (type) | Keys |
|---|---|---|---|
| `roles` | 3 | id, name varchar(50), description varchar(200) | UNIQUE(name) |
| `users` | 2 | id, email varchar(255), full_name, hashed_password, is_active, role_id, created_at, updated_at | UNIQUE(email); FK role_id -> roles |
| `app_settings` | 2 | key varchar(100) PK, value **jsonb**, updated_at, updated_by | FK updated_by -> users (SET NULL) |
| `alembic_version` | 1 | version_num | migration bookkeeping |

### 1.2 Company knowledge base
| Table | Rows | Columns (type) | Keys |
|---|---|---|---|
| `clients` | 6 | id, name varchar(300), industry, country, contact_email, notes, created_at, updated_at | none beyond PK |
| `projects` | 7 | id, name, **client_id integer**, description, **technologies json**, team_size, duration_weeks, total_value **double**, status varchar(50), created_at, updated_at | **no FK on client_id** |
| `employees` | 12 | id, name, role, level, **skills json**, hourly_rate **double**, is_active, created_at, updated_at | none |
| `technologies` | 24 | id, name varchar(200), category, proficiency, created_at, updated_at | UNIQUE(name) |
| `certifications` | 6 | id, name, issuing_body, certificate_number, **valid_until varchar(50)**, document_path, created_at, updated_at | none |
| `financial_records` | 0 | id, fiscal_year int, annual_turnover **double**, net_profit **double**, currency varchar(10), notes, created_at (nullable), updated_at (nullable) | none |
| `cost_parameters` | 10 | id, role, level, hourly_rate **double**, qa/devops/contingency/profit_margin_percentage **double**, created_at, updated_at | no unique on (role, level) |
| `project_documents` | 0 | id, project_id, doc_category, original_filename, file_path, mime_type, page_count, file_size_bytes, is_processed, processing_error, created_at, updated_at | FK project_id -> projects (CASCADE) |
| `project_document_chunks` | 0 | id, project_document_id, project_id, chunk_index, chunk_text, page_number, section_heading, doc_category, chunk_metadata jsonb, **embedding text**, created_at | FKs -> project_documents, projects (CASCADE) |

### 1.3 Documents and tender analysis
| Table | Rows | Columns (type) | Keys |
|---|---|---|---|
| `documents` | 13 | id, filename, original_filename, file_path varchar(1000), mime_type, page_count, doc_type **enum**, status **enum**, extracted_text text, uploaded_by, created_at, updated_at | FK uploaded_by -> users |
| `tender_chunks` | 0 | id, document_id, chunk_index, chunk_text, page_number, section_heading, chunk_metadata jsonb, **embedding text**, created_at (nullable) | FK document_id -> documents (CASCADE); index on document_id |
| `eligibility_reports` | 13 | id, document_id, status **enum**, **criteria json**, **compliance_matrix json**, missing_documents json, summary text, created_at, updated_at | FK document_id -> documents |
| `proposals` | 0 | id, document_id, eligibility_report_id, technical_proposal, commercial_proposal, company_profile, sections json, docx_path, pdf_path, created_at, updated_at | FKs -> documents, eligibility_reports |

### 1.4 Estimation
Two separate estimation systems exist side by side.

| Table | Rows | Columns (type) | Keys |
|---|---|---|---|
| `estimation_reports` | 0 | id, document_id, modules_count, total_hours **double**, total_weeks, modules json, sprints json, tasks json, created_at, updated_at | FK document_id -> documents |
| `cost_sheets` | 0 | id, estimation_id, developer/qa/devops/infrastructure/storage cost **double**, contingency, profit_margin, total_cost, suggested_bid **double**, line_items json, created_at, updated_at | FK estimation_id -> estimation_reports |
| `estimation_projects` | 0 | id, name, document_id, status varchar(50), notes, about 12 percentage and cost columns **double**, created_at, updated_at | FK document_id -> documents |
| `estimation_features` | 0 | id, project_id, sort_order, milestone, module, sub_module, feature, four complexity varchar(20), hours **double** x5 | FK project_id -> estimation_projects (CASCADE) |
| `estimation_resources` | 0 | id, project_id, sort_order, role, responsibility, count, effort_hours, effort_pct, hourly_rate, total_cost **double**, is_active | FK project_id -> estimation_projects (CASCADE) |

### 1.5 Tender Tiger (copied in on 2026-10-12, unmanaged by Alembic)
| Table | Rows | Columns | Keys |
|---|---|---|---|
| `tt_tenders` | 38 | **38 columns**: tid text, organization, dept_tender_number, tender_title, product_description, key_location, tender_type, **worth text + worth_amount**, **emd + emd_amount**, **doc_fees + doc_fee_amount**, quantity, due_date, **days_to_go**, startup_relaxation, **folder_name, path, files jsonb, download_status, raw_detail text (34 KB total), scraped_at**, dept_tender_link, tender_description, department, opening_date, published_date, tender_link, **files_path, zip_path, file_count, documents_listed jsonb, meta_version**, first_seen_at, dept_link_type, dept_portal_url, dept_link_hint, **files_in_db** | UNIQUE(tid) |
| `tt_tender_files` | 202 | id, tid text, file_name, kind ('file'/'zip'), size, sha256, **content bytea (about 388 MB)**, stored_at | UNIQUE(tid, kind, file_name); **no FK to tt_tenders** |
| `tt_failures` | 2 | id, tid, url, error (page dump), failed_at | **no FK** |

### 1.6 Relationships today (all declared foreign keys)
```
roles <- users <- documents <- eligibility_reports <- proposals
                       ^  ^---- estimation_reports <- cost_sheets
                       |  `---- estimation_projects <- estimation_features / estimation_resources
                       `------- tender_chunks
projects <- project_documents <- project_document_chunks
clients      (nothing points to it: projects.client_id is a plain integer)
tt_*         (not connected to anything)
```

---

## 2. What is wrong with it (findings)

Evidence comes from the live data.

| # | Finding | Evidence | Why it matters |
|---|---|---|---|
| F1 | Tender Tiger tables have no relationships | 9 files in `tt_tender_files` belong to 3 `tid`s that have no row in `tt_tenders`; 2 of those are in `tt_failures` | Orphans accumulate silently; nothing stops a bad delete |
| F2 | Scraper plumbing mixed with business data | `tt_tenders` has 38 columns incl. local disk paths (`path`, `files_path`, `zip_path`), `meta_version`, `raw_detail` | The business table is wide and half of it means nothing to the app |
| F3 | The same fact stored twice | `worth` text + `worth_amount`; same for EMD and fees; `files` and `documents_listed` JSON repeat `tt_tender_files`; `file_count` vs `files_in_db` disagree on 38 of 38 rows; `days_to_go` is frozen at scrape time | Copies drift apart; already wrong today |
| F4 | Money stored as `double precision` | `total_value`, `hourly_rate`, `annual_turnover`, all cost sheet and estimation amounts | Floating point rounding on currency; 0.1 + 0.2 problem |
| F5 | `projects.client_id` has no foreign key | FK list has no `projects -> clients` | A client can be deleted while projects still point to it. Today there are 0 orphans, so the constraint can be added safely |
| F6 | Skills and technologies are JSON, not relations | `employees.skills json`, `projects.technologies json`; a `technologies` table exists but nothing links to it | "Which projects used React?" (the KB Search use case) cannot use an index or a join; spelling drift ("React" / "ReactJS") is not controlled |
| F7 | Dates stored as text | `certifications.valid_until varchar(50)` (values are all ISO dates: 2025-09-30 ... 2027-06-30) | Cannot be compared or sorted safely; the rule engine needs special handling for unreadable dates |
| F8 | Foreign keys are not indexed | Only 5 secondary indexes exist in total; `eligibility_reports.document_id`, `proposals.document_id`, `estimation_*.project_id`, `projects.client_id`, `documents.uploaded_by`, `users.role_id` have none | Postgres does not index FK columns automatically; joins and cascade deletes scan whole tables as data grows |
| F9 | Missing uniqueness | `cost_parameters (role, level)`, `clients.name`, `financial_records (fiscal_year)` are not unique | Duplicate rate rows or duplicate years would silently double-count. Today there are 0 duplicates, so constraints can be added |
| F10 | Free-text status columns | `projects.status`, `estimation_projects.status`, complexity columns are `varchar` | Typos are accepted; only `documents` and `eligibility_reports` use enums |
| F11 | Inconsistent null rules | `created_at` is nullable on `financial_records`, `project_documents`, `project_document_chunks`, `tender_chunks`, but NOT NULL elsewhere | Audit information is unreliable |
| F12 | Embeddings stored as `text` | `tender_chunks.embedding`, `project_document_chunks.embedding` | Text is bigger and cannot be searched by similarity. **pgvector 0.8.6 is available on this server** (checked) |
| F13 | `json` instead of `jsonb` | skills, technologies, criteria, compliance_matrix, line_items, modules, sprints, tasks, sections | `json` is re-parsed on every read and cannot be indexed |
| F14 | Report results live in one JSON blob | `eligibility_reports.criteria` holds every evaluated criterion; `compliance_matrix` mixes run state, stage output and metrics | Cannot ask "which requirement fails most often across tenders?" without parsing JSON in code |
| F15 | Big text and file facts sit on the main table | `documents.extracted_text` (can be 1000 pages) beside metadata; no `sha256`/`size` on `documents` | Every `SELECT *` on `documents` loads full text; no way to detect the same file uploaded twice |
| F16 | File bytes beside metadata | `tt_tender_files.content` bytea in the same table as names, sizes, hashes | Careless `SELECT *` loads about 388 MB |
| F17 | 44% of stored bytes are probably duplicates | 41 zip files (171 MB) "contain all documents", and the same documents are also stored loose | To be verified before any removal |
| F18 | No audit trail | No table records who changed or deleted what | CLAUDE.md asks for role-based access and traceable results |
| F19 | Two estimation systems | `estimation_reports + cost_sheets` (AI, by document) and `estimation_projects + features + resources` (spreadsheet style) | Not a defect by itself; documented so nobody merges them by accident. No change proposed |

---

## 3. Target schema (new)

Rules used for every table:
- Existing tables keep their `integer` keys; there is no benefit in migrating them. New tables that may grow large use `bigint`.
- Foreign keys always declared, always indexed.
- Money is `numeric(18,2)`; percentages `numeric(6,3)`; hours `numeric(10,2)`.
- `created_at` and `updated_at` are `timestamptz NOT NULL DEFAULT now()` everywhere.
- Free-text status becomes a `CHECK` constraint (simpler to change than a Postgres enum).

### 3.1 Tender Tiger: new schema `tiger` (replaces `tt_*`)

```sql
CREATE SCHEMA tiger;

CREATE TABLE tiger.organization (
  id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name  text NOT NULL,
  CONSTRAINT organization_name_uq UNIQUE (name)
);

CREATE TABLE tiger.tender (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tid                 text   NOT NULL UNIQUE,                 -- Tender Tiger's own ID
  organization_id     bigint REFERENCES tiger.organization(id),
  department          text,
  dept_tender_number  text,
  title               text,
  scope_description   text,                                   -- was tender_description
  item_description    text,                                   -- was product_description
  tender_type         text,
  quantity            text,
  city text, state text, country text DEFAULT 'India',
  location_raw        text,                                   -- original "City, State, India"
  estimated_value     numeric(18,2) CHECK (estimated_value >= 0),
  emd_amount          numeric(18,2) CHECK (emd_amount >= 0),
  doc_fee_amount      numeric(18,2) CHECK (doc_fee_amount >= 0),
  startup_relaxation  text,
  published_date date, due_date date, opening_date date,
  source_url          text,                                   -- was tender_link
  dept_url            text,
  ingest_status       text NOT NULL DEFAULT 'complete' CHECK (ingest_status IN ('complete','incomplete','failed')),
  scraped_at          timestamptz,
  first_seen_at       timestamptz NOT NULL DEFAULT now(),
  search_tsv          tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', coalesce(title,'')||' '||coalesce(department,'')||' '||coalesce(city,'')||' '||coalesce(state,''))) STORED,
  CHECK (ingest_status <> 'complete' OR title IS NOT NULL)
);
CREATE INDEX ON tiger.tender (due_date);
CREATE INDEX ON tiger.tender (organization_id);
CREATE INDEX ON tiger.tender (state);
CREATE INDEX ON tiger.tender USING gin (search_tsv);

CREATE TABLE tiger.tender_raw (                               -- bulky scraper data, kept but out of the way
  tender_id        bigint PRIMARY KEY REFERENCES tiger.tender(id) ON DELETE CASCADE,
  raw_text         text,
  listed_documents jsonb,                                     -- was documents_listed
  scrape_meta      jsonb                                      -- meta_version, dept_link_type, dept_link_hint
);

CREATE TABLE tiger.tender_file (                              -- metadata only
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tender_id   bigint NOT NULL REFERENCES tiger.tender(id) ON DELETE CASCADE,
  file_name   text   NOT NULL,
  role        text   NOT NULL CHECK (role IN ('document','archive')),   -- was kind file/zip
  extension   text   NOT NULL,
  mime_type   text   NOT NULL,
  size_bytes  bigint NOT NULL CHECK (size_bytes >= 0),
  sha256      char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  stored_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tender_id, role, file_name)
);
CREATE INDEX ON tiger.tender_file (tender_id);
CREATE INDEX ON tiger.tender_file (sha256);

CREATE TABLE tiger.file_blob (                                -- the bytes, isolated
  file_id  bigint PRIMARY KEY REFERENCES tiger.tender_file(id) ON DELETE CASCADE,
  content  bytea NOT NULL
);

CREATE TABLE tiger.ingest_failure (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tender_id   bigint REFERENCES tiger.tender(id) ON DELETE SET NULL,
  tid         text NOT NULL,
  source_url  text,
  error       text NOT NULL,
  failed_at   timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE tiger.file_analysis (                            -- real link from a stored file to the analysis of it
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tender_file_id bigint  NOT NULL REFERENCES tiger.tender_file(id) ON DELETE CASCADE,
  document_id    integer NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id)
);

CREATE VIEW tiger.v_tender AS                                 -- what the app reads
SELECT t.*, o.name AS organization,
       (t.due_date - CURRENT_DATE) AS days_left,
       (t.due_date >= CURRENT_DATE) AS is_open,
       (SELECT count(*) FROM tiger.tender_file f WHERE f.tender_id = t.id AND f.role = 'document') AS document_count
FROM tiger.tender t LEFT JOIN tiger.organization o ON o.id = t.organization_id;
```

### 3.2 Knowledge base: changes to existing tables

```sql
-- relationships
ALTER TABLE projects ADD CONSTRAINT projects_client_fk FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL;

CREATE TABLE project_technology (                              -- replaces projects.technologies json
  project_id    integer NOT NULL REFERENCES projects(id)     ON DELETE CASCADE,
  technology_id integer NOT NULL REFERENCES technologies(id) ON DELETE RESTRICT,
  PRIMARY KEY (project_id, technology_id)
);
CREATE TABLE employee_skill (                                  -- replaces employees.skills json
  employee_id   integer NOT NULL REFERENCES employees(id)    ON DELETE CASCADE,
  technology_id integer NOT NULL REFERENCES technologies(id) ON DELETE RESTRICT,
  proficiency   text,
  PRIMARY KEY (employee_id, technology_id)
);

-- types
ALTER TABLE projects          ALTER COLUMN total_value TYPE numeric(18,2);
ALTER TABLE employees         ALTER COLUMN hourly_rate TYPE numeric(10,2);
ALTER TABLE financial_records ALTER COLUMN annual_turnover TYPE numeric(18,2), ALTER COLUMN net_profit TYPE numeric(18,2);
ALTER TABLE cost_parameters   ALTER COLUMN hourly_rate TYPE numeric(10,2);   -- and the four percentage columns -> numeric(6,3)
ALTER TABLE certifications    ADD COLUMN valid_until_date date;              -- filled from valid_until; old text column kept until the code is switched

-- integrity
ALTER TABLE cost_parameters   ADD CONSTRAINT cost_parameters_role_level_uq UNIQUE (role, level);
ALTER TABLE financial_records ADD CONSTRAINT financial_records_year_uq UNIQUE (fiscal_year, currency);
CREATE UNIQUE INDEX clients_name_uq ON clients (lower(name));
ALTER TABLE projects ADD CONSTRAINT projects_status_ck CHECK (status IN ('active','completed'));   -- the only values in the data; the code defaults to 'completed'. Add more only if the UI offers them

-- not-null timestamps
ALTER TABLE financial_records         ALTER COLUMN created_at SET NOT NULL, ALTER COLUMN updated_at SET NOT NULL;  -- same for project_documents, project_document_chunks, tender_chunks

-- embeddings (pgvector is installed)
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE tender_chunks           ADD COLUMN embedding_vec vector;  -- dimension fixed once the embedding model is chosen
ALTER TABLE project_document_chunks ADD COLUMN embedding_vec vector;
```

### 3.3 Documents and tender analysis

```sql
ALTER TABLE documents ADD COLUMN sha256 char(64), ADD COLUMN size_bytes bigint;
CREATE INDEX ON documents (uploaded_by);
CREATE INDEX ON documents (status);
CREATE INDEX ON documents (sha256);

CREATE TABLE document_text (                                   -- big text off the main table
  document_id integer PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  text        text NOT NULL
);

CREATE TABLE eligibility_result (                              -- one row per evaluated criterion
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  report_id      integer NOT NULL REFERENCES eligibility_reports(id) ON DELETE CASCADE,
  criterion_id   text    NOT NULL,                            -- C001 ...
  page_no        integer,
  field          text    NOT NULL,
  operator       text,
  tender_value   jsonb,
  company_value  text,
  status         text    NOT NULL CHECK (status IN ('PASS','FAIL','MISSING','NEEDS_REVIEW','INFORMATIONAL')),
  mandatory      boolean NOT NULL DEFAULT true,
  grounded       boolean NOT NULL DEFAULT true,
  source_text    text,
  reasoning      text,
  UNIQUE (report_id, criterion_id)
);
CREATE INDEX ON eligibility_result (status);
CREATE INDEX ON eligibility_result (field);

CREATE INDEX ON eligibility_reports (document_id);
CREATE INDEX ON proposals (document_id);
CREATE INDEX ON proposals (eligibility_report_id);
-- criteria / compliance_matrix / missing_documents / sections / modules / sprints / tasks / line_items / skills / technologies: json -> jsonb
```

### 3.4 Estimation (types and indexes only)

```sql
-- money and hours: double precision -> numeric across estimation_*, cost_sheets
CREATE INDEX ON estimation_features  (project_id, sort_order);
CREATE INDEX ON estimation_resources (project_id, sort_order);
CREATE INDEX ON estimation_projects  (document_id);
CREATE INDEX ON estimation_reports   (document_id);
CREATE INDEX ON cost_sheets          (estimation_id);
ALTER TABLE estimation_projects ADD CONSTRAINT estimation_projects_status_ck CHECK (status IN ('draft','finalized'));   -- as documented in app/models/estimation_project.py
```

### 3.5 Platform

```sql
CREATE INDEX ON users (role_id);

CREATE TABLE audit_log (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  at          timestamptz NOT NULL DEFAULT now(),
  user_id     integer REFERENCES users(id) ON DELETE SET NULL,
  action      text NOT NULL,            -- 'login', 'upload', 'delete', 'analyse', 'settings.update' ...
  entity      text,                     -- table name
  entity_id   text,
  detail      jsonb
);
CREATE INDEX ON audit_log (at DESC);
CREATE INDEX ON audit_log (user_id);
CREATE INDEX ON audit_log (entity, entity_id);
```

---

## 4. Change list: old, new, and why

| # | Old | New | Why | Impact on application code |
|---|---|---|---|---|
| C1 | `tt_tenders`, `tt_tender_files`, `tt_failures` in `public` | schema `tiger` with `organization`, `tender`, `tender_raw`, `tender_file`, `file_blob`, `ingest_failure`, `file_analysis`, view `v_tender` | F1, F2, F3, F16: relationships, no duplicated facts, bytes separated, scraper data kept but out of the business table | `backend/app/api/v1/tender_tiger.py` only (queries switch to the new names) |
| C2 | 38 columns in one tender table | about 25 business columns + a separate raw table | F2 | same file |
| C3 | text and numeric copies of value, EMD, fee | numeric only | F3 | same file |
| C4 | `days_to_go`, `file_count`, `files_in_db` stored | computed in `v_tender` | F3: stored copies go stale | same file |
| C5 | `key_location` as one string | `city`, `state`, `country` + original kept in `location_raw` | State filter becomes an indexed column | same file |
| C6 | `organization` repeated as text | `tiger.organization` + FK | One spelling per buyer; fast filter | same file |
| C7 | `kind` = file / zip | `role` = document / archive, plus `extension`, `mime_type` | Tells file type without opening it | same file |
| C8 | filename match between `documents` and `tt_tender_files` | `tiger.file_analysis` with real FKs | F1: file names are not unique across tenders | the Analyse endpoint writes one extra row |
| C9 | `projects.client_id` plain integer | FK to `clients` | F5 | none (0 orphans today) |
| C10 | `projects.technologies json`, `employees.skills json` | `project_technology`, `employee_skill` link tables | F6: indexed "who/what used React", controlled names | KB pages and KB Search read and write these (phase 3, needs code change) |
| C11 | `double precision` money, hours and percentages | `numeric(18,2)` / `numeric(10,2)` / `numeric(6,3)` | F4: exact arithmetic for bids and cost sheets | Python receives `Decimal`; API and cost calculation code must convert (phase 2) |
| C12 | `certifications.valid_until` varchar | `valid_until_date date` (old column kept) | F7 | rule engine switches to the date column (phase 2) |
| C13 | no uniqueness on cost rates, client names, fiscal years | UNIQUE constraints | F9: stops silent duplicates | forms must show a clear message on a duplicate |
| C14 | free-text status on projects and estimation | CHECK constraints | F10 | none if values match what the code writes |
| C15 | nullable `created_at` on four tables | NOT NULL with default | F11 | none |
| C16 | no FK indexes | indexes on every FK column | F8: Postgres does not create them | none |
| C17 | `embedding text` | `embedding_vec vector` (pgvector) | F12: real similarity search, smaller storage | chunking/search code (phase 3, after the embedding model is fixed) |
| C18 | `json` columns | `jsonb` | F13 | none for reads and writes through SQLAlchemy |
| C19 | criteria inside one JSON blob | `eligibility_result` rows (JSON kept during transition) | F14: analytics across tenders; "which requirement fails most" | report writer writes both during transition; reader moves later (phase 3) |
| C20 | `documents.extracted_text` on the main row; no hash | `document_text` table; `sha256`, `size_bytes` | F15 | upload and pipeline code reads/writes text from the new table (phase 3) |
| C21 | no audit | `audit_log` | F18 | new writes from auth, upload, delete, analyse, settings (phase 3) |
| C22 | two estimation systems | **unchanged** | F19: merging changes behaviour | none |

---

## 5. How to get there safely

Everything goes through Alembic migrations (CLAUDE.md requires migration scripts) and every phase starts with a `pg_dump`.

**Phase 1: additive, no behaviour change.** Create the `tiger` schema and copy the data in one transaction, then compare row counts, file sizes, sha256 values and amounts against `tt_*`. Add the missing FK indexes, the `projects.client_id` FK, the `NOT NULL` timestamp fixes, and the UNIQUE/CHECK constraints (each one is checked against the data first; all pass today). Only `tender_tiger.py` is switched to the new tables. The `tt_*` tables stay until you confirm the screens, so rollback is pointing the code back.

**Phase 2: type changes.** `double precision` to `numeric`, `valid_until` to a real date, `json` to `jsonb`. These touch Python code that does arithmetic or compares dates, so each is done one table at a time with tests, and the old column stays until the code reads the new one.

**Phase 3: structural.** Link tables for skills and technologies, `eligibility_result`, `document_text`, `audit_log`, and pgvector columns. Each needs code changes in the app, so each is its own piece of work, written to run old and new side by side first.

Rollback for every phase: restore from the backup taken at its start, or (phases 1 and 2) point the code back at the old column or table, which is kept until sign-off.

### Open decisions
1. **Zip archives (171 MB).** Keep them as `role = 'archive'`. Remove only after a check shows every zip entry matches a loose file.
2. **The 3 orphan tenders** (9 files): insert stub tenders with `ingest_status = 'incomplete'` so the files are kept, or drop those files.
3. **Schema name:** `tiger` (proposed) or `public` with a `tt_` prefix.
4. **Embedding dimension** for pgvector: depends on the embedding model (`nomic-embed-text` is 768).
5. **Allowed status values.** `estimation_projects` is `draft` / `finalized` (from the model). `projects` holds `active` and `completed` today; confirm whether the UI can set others before adding the CHECK.

---

## Appendix A. Complete current schema (exact, from the live database)

Generated from `information_schema` and `pg_indexes` on 2026-10-12. Types are as Postgres reports them; `USER-DEFINED` is a Postgres enum (`documenttype`: SRS, TENDER, PROPOSAL, RFP, UNKNOWN; `documentstatus`: UPLOADED, PROCESSING, ANALYZED, FAILED; `eligibilitystatus`: ELIGIBLE, NOT_ELIGIBLE, PARTIAL, PENDING).


### `alembic_version` (1 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `version_num` | character varying(32) | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX alembic_version_pkc ON alembic_version USING btree (version_num)`

### `app_settings` (2 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `key` | character varying(100) | NOT NULL |  |
| 2 | `value` | jsonb | NOT NULL |  |
| 3 | `updated_at` | timestamp with time zone | NOT NULL | `now()` |
| 4 | `updated_by` | integer | null |  |

Foreign keys: `updated_by -> users(id) ON DELETE SET NULL`

Indexes:
- `CREATE UNIQUE INDEX app_settings_pkey ON app_settings USING btree (key)`

### `certifications` (6 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'certifications_id_seq'` |
| 2 | `name` | character varying(300) | NOT NULL |  |
| 3 | `issuing_body` | character varying(300) | null |  |
| 4 | `certificate_number` | character varying(200) | null |  |
| 5 | `valid_until` | character varying(50) | null |  |
| 6 | `document_path` | character varying(1000) | null |  |
| 7 | `created_at` | timestamp with time zone | NOT NULL |  |
| 8 | `updated_at` | timestamp with time zone | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX certifications_pkey ON certifications USING btree (id)`

### `clients` (6 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'clients_id_seq'` |
| 2 | `name` | character varying(300) | NOT NULL |  |
| 3 | `industry` | character varying(200) | null |  |
| 4 | `country` | character varying(100) | null |  |
| 5 | `contact_email` | character varying(255) | null |  |
| 6 | `notes` | text | null |  |
| 7 | `created_at` | timestamp with time zone | NOT NULL |  |
| 8 | `updated_at` | timestamp with time zone | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX clients_pkey ON clients USING btree (id)`

### `cost_parameters` (10 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'cost_parameters_id_seq'` |
| 2 | `role` | character varying(100) | NOT NULL |  |
| 3 | `level` | character varying(50) | NOT NULL |  |
| 4 | `hourly_rate` | double precision | NOT NULL |  |
| 5 | `qa_percentage` | double precision | NOT NULL |  |
| 6 | `devops_percentage` | double precision | NOT NULL |  |
| 7 | `contingency_percentage` | double precision | NOT NULL |  |
| 8 | `profit_margin_percentage` | double precision | NOT NULL |  |
| 9 | `created_at` | timestamp with time zone | NOT NULL |  |
| 10 | `updated_at` | timestamp with time zone | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX cost_parameters_pkey ON cost_parameters USING btree (id)`

### `cost_sheets` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'cost_sheets_id_seq'` |
| 2 | `estimation_id` | integer | NOT NULL |  |
| 3 | `developer_cost` | double precision | NOT NULL |  |
| 4 | `qa_cost` | double precision | NOT NULL |  |
| 5 | `devops_cost` | double precision | NOT NULL |  |
| 6 | `infrastructure_cost` | double precision | NOT NULL |  |
| 7 | `storage_cost` | double precision | NOT NULL |  |
| 8 | `contingency` | double precision | NOT NULL |  |
| 9 | `profit_margin` | double precision | NOT NULL |  |
| 10 | `total_cost` | double precision | NOT NULL |  |
| 11 | `suggested_bid` | double precision | NOT NULL |  |
| 12 | `line_items` | json | null |  |
| 13 | `created_at` | timestamp with time zone | NOT NULL |  |
| 14 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `estimation_id -> estimation_reports(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX cost_sheets_pkey ON cost_sheets USING btree (id)`

### `documents` (13 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'documents_id_seq'` |
| 2 | `filename` | character varying(500) | NOT NULL |  |
| 3 | `original_filename` | character varying(500) | NOT NULL |  |
| 4 | `file_path` | character varying(1000) | NOT NULL |  |
| 5 | `mime_type` | character varying(100) | null |  |
| 6 | `page_count` | integer | null |  |
| 7 | `doc_type` | USER-DEFINED | NOT NULL |  |
| 8 | `status` | USER-DEFINED | NOT NULL |  |
| 9 | `extracted_text` | text | null |  |
| 10 | `uploaded_by` | integer | NOT NULL |  |
| 11 | `created_at` | timestamp with time zone | NOT NULL |  |
| 12 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `uploaded_by -> users(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX documents_pkey ON documents USING btree (id)`

### `eligibility_reports` (13 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'eligibility_reports_id_seq'` |
| 2 | `document_id` | integer | NOT NULL |  |
| 3 | `status` | USER-DEFINED | NOT NULL |  |
| 4 | `criteria` | json | null |  |
| 5 | `compliance_matrix` | json | null |  |
| 6 | `missing_documents` | json | null |  |
| 7 | `summary` | text | null |  |
| 8 | `created_at` | timestamp with time zone | NOT NULL |  |
| 9 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `document_id -> documents(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX eligibility_reports_pkey ON eligibility_reports USING btree (id)`

### `employees` (12 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'employees_id_seq'` |
| 2 | `name` | character varying(300) | NOT NULL |  |
| 3 | `role` | character varying(200) | NOT NULL |  |
| 4 | `level` | character varying(50) | null |  |
| 5 | `skills` | json | null |  |
| 6 | `hourly_rate` | double precision | null |  |
| 7 | `is_active` | boolean | NOT NULL |  |
| 8 | `created_at` | timestamp with time zone | NOT NULL |  |
| 9 | `updated_at` | timestamp with time zone | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX employees_pkey ON employees USING btree (id)`

### `estimation_features` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'estimation_features_id_seq'` |
| 2 | `project_id` | integer | NOT NULL |  |
| 3 | `sort_order` | integer | NOT NULL |  |
| 4 | `milestone` | character varying(200) | null |  |
| 5 | `module` | character varying(200) | null |  |
| 6 | `sub_module` | character varying(200) | null |  |
| 7 | `feature` | character varying(500) | NOT NULL |  |
| 8 | `data_model_complexity` | character varying(20) | null |  |
| 9 | `api_complexity` | character varying(20) | null |  |
| 10 | `business_rules_complexity` | character varying(20) | null |  |
| 11 | `ui_complexity` | character varying(20) | null |  |
| 12 | `fixed_hours` | double precision | NOT NULL |  |
| 13 | `base_hours` | double precision | NOT NULL |  |
| 14 | `total_dev_hours` | double precision | NOT NULL |  |
| 15 | `total_qa_hours` | double precision | NOT NULL |  |
| 16 | `total_hours` | double precision | NOT NULL |  |

Foreign keys: `project_id -> estimation_projects(id) ON DELETE CASCADE`

Indexes:
- `CREATE UNIQUE INDEX estimation_features_pkey ON estimation_features USING btree (id)`

### `estimation_projects` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'estimation_projects_id_seq'` |
| 2 | `name` | character varying(500) | NOT NULL |  |
| 3 | `document_id` | integer | null |  |
| 4 | `status` | character varying(50) | NOT NULL |  |
| 5 | `notes` | text | null |  |
| 6 | `complexity_pct` | double precision | NOT NULL |  |
| 7 | `unit_testing_pct` | double precision | NOT NULL |  |
| 8 | `rework_pct` | double precision | NOT NULL |  |
| 9 | `pm_pct` | double precision | NOT NULL |  |
| 10 | `design_arch_pct` | double precision | NOT NULL |  |
| 11 | `spec_uiux_pct` | double precision | NOT NULL |  |
| 12 | `dev_buffer_pct` | double precision | NOT NULL |  |
| 13 | `margin_pct` | double precision | NOT NULL |  |
| 14 | `infra_cost` | double precision | NOT NULL |  |
| 15 | `total_dev_hours` | double precision | NOT NULL |  |
| 16 | `total_qa_hours` | double precision | NOT NULL |  |
| 17 | `grand_total_hours` | double precision | NOT NULL |  |
| 18 | `internal_cost` | double precision | NOT NULL |  |
| 19 | `margin_amount` | double precision | NOT NULL |  |
| 20 | `total_project_cost` | double precision | NOT NULL |  |
| 21 | `created_at` | timestamp with time zone | NOT NULL |  |
| 22 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `document_id -> documents(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX estimation_projects_pkey ON estimation_projects USING btree (id)`

### `estimation_reports` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'estimation_reports_id_seq'` |
| 2 | `document_id` | integer | NOT NULL |  |
| 3 | `modules_count` | integer | NOT NULL |  |
| 4 | `total_hours` | double precision | NOT NULL |  |
| 5 | `total_weeks` | integer | NOT NULL |  |
| 6 | `modules` | json | null |  |
| 7 | `sprints` | json | null |  |
| 8 | `tasks` | json | null |  |
| 9 | `created_at` | timestamp with time zone | NOT NULL |  |
| 10 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `document_id -> documents(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX estimation_reports_pkey ON estimation_reports USING btree (id)`

### `estimation_resources` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'estimation_resources_id_seq'` |
| 2 | `project_id` | integer | NOT NULL |  |
| 3 | `sort_order` | integer | NOT NULL |  |
| 4 | `role` | character varying(200) | NOT NULL |  |
| 5 | `responsibility` | character varying(500) | null |  |
| 6 | `count` | integer | NOT NULL |  |
| 7 | `effort_hours` | double precision | NOT NULL |  |
| 8 | `effort_pct` | double precision | NOT NULL |  |
| 9 | `hourly_rate` | double precision | NOT NULL |  |
| 10 | `total_cost` | double precision | NOT NULL |  |
| 11 | `is_active` | boolean | NOT NULL | `true` |

Foreign keys: `project_id -> estimation_projects(id) ON DELETE CASCADE`

Indexes:
- `CREATE UNIQUE INDEX estimation_resources_pkey ON estimation_resources USING btree (id)`

### `financial_records` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'financial_records_id_seq'` |
| 2 | `fiscal_year` | integer | NOT NULL |  |
| 3 | `annual_turnover` | double precision | NOT NULL |  |
| 4 | `net_profit` | double precision | null |  |
| 5 | `currency` | character varying(10) | NOT NULL |  |
| 6 | `notes` | text | null |  |
| 7 | `created_at` | timestamp with time zone | null |  |
| 8 | `updated_at` | timestamp with time zone | null |  |

Indexes:
- `CREATE UNIQUE INDEX financial_records_pkey ON financial_records USING btree (id)`

### `project_document_chunks` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'project_document_chunks_id_seq'` |
| 2 | `project_document_id` | integer | NOT NULL |  |
| 3 | `project_id` | integer | NOT NULL |  |
| 4 | `chunk_index` | integer | NOT NULL |  |
| 5 | `chunk_text` | text | NOT NULL |  |
| 6 | `page_number` | integer | null |  |
| 7 | `section_heading` | character varying(500) | null |  |
| 8 | `doc_category` | character varying(50) | null |  |
| 9 | `chunk_metadata` | jsonb | null |  |
| 10 | `embedding` | text | null |  |
| 11 | `created_at` | timestamp with time zone | null |  |

Foreign keys: `project_document_id -> project_documents(id) ON DELETE CASCADE`; `project_id -> projects(id) ON DELETE CASCADE`

Indexes:
- `CREATE UNIQUE INDEX project_document_chunks_pkey ON project_document_chunks USING btree (id)`

### `project_documents` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'project_documents_id_seq'` |
| 2 | `project_id` | integer | NOT NULL |  |
| 3 | `doc_category` | character varying(50) | NOT NULL |  |
| 4 | `original_filename` | character varying(500) | NOT NULL |  |
| 5 | `file_path` | character varying(1000) | NOT NULL |  |
| 6 | `mime_type` | character varying(100) | null |  |
| 7 | `page_count` | integer | null |  |
| 8 | `file_size_bytes` | integer | null |  |
| 9 | `is_processed` | boolean | NOT NULL |  |
| 10 | `processing_error` | text | null |  |
| 11 | `created_at` | timestamp with time zone | null |  |
| 12 | `updated_at` | timestamp with time zone | null |  |

Foreign keys: `project_id -> projects(id) ON DELETE CASCADE`

Indexes:
- `CREATE INDEX ix_project_documents_project_id ON project_documents USING btree (project_id)`
- `CREATE UNIQUE INDEX project_documents_pkey ON project_documents USING btree (id)`

### `projects` (7 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'projects_id_seq'` |
| 2 | `name` | character varying(500) | NOT NULL |  |
| 3 | `client_id` | integer | null |  |
| 4 | `description` | text | null |  |
| 5 | `technologies` | json | null |  |
| 6 | `team_size` | integer | null |  |
| 7 | `duration_weeks` | integer | null |  |
| 8 | `total_value` | double precision | null |  |
| 9 | `status` | character varying(50) | NOT NULL |  |
| 10 | `created_at` | timestamp with time zone | NOT NULL |  |
| 11 | `updated_at` | timestamp with time zone | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX projects_pkey ON projects USING btree (id)`

### `proposals` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'proposals_id_seq'` |
| 2 | `document_id` | integer | NOT NULL |  |
| 3 | `eligibility_report_id` | integer | null |  |
| 4 | `technical_proposal` | text | null |  |
| 5 | `commercial_proposal` | text | null |  |
| 6 | `company_profile` | text | null |  |
| 7 | `sections` | json | null |  |
| 8 | `docx_path` | character varying(1000) | null |  |
| 9 | `pdf_path` | character varying(1000) | null |  |
| 10 | `created_at` | timestamp with time zone | NOT NULL |  |
| 11 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `document_id -> documents(id) ON DELETE NO ACTION`; `eligibility_report_id -> eligibility_reports(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX proposals_pkey ON proposals USING btree (id)`

### `roles` (3 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'roles_id_seq'` |
| 2 | `name` | character varying(50) | NOT NULL |  |
| 3 | `description` | character varying(200) | null |  |

Indexes:
- `CREATE UNIQUE INDEX roles_name_key ON roles USING btree (name)`
- `CREATE UNIQUE INDEX roles_pkey ON roles USING btree (id)`

### `technologies` (24 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'technologies_id_seq'` |
| 2 | `name` | character varying(200) | NOT NULL |  |
| 3 | `category` | character varying(100) | null |  |
| 4 | `proficiency` | character varying(50) | null |  |
| 5 | `created_at` | timestamp with time zone | NOT NULL |  |
| 6 | `updated_at` | timestamp with time zone | NOT NULL |  |

Indexes:
- `CREATE UNIQUE INDEX technologies_name_key ON technologies USING btree (name)`
- `CREATE UNIQUE INDEX technologies_pkey ON technologies USING btree (id)`

### `tender_chunks` (0 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'tender_chunks_id_seq'` |
| 2 | `document_id` | integer | NOT NULL |  |
| 3 | `chunk_index` | integer | NOT NULL |  |
| 4 | `chunk_text` | text | NOT NULL |  |
| 5 | `page_number` | integer | null |  |
| 6 | `section_heading` | character varying(500) | null |  |
| 7 | `chunk_metadata` | jsonb | null |  |
| 8 | `embedding` | text | null |  |
| 9 | `created_at` | timestamp with time zone | null |  |

Foreign keys: `document_id -> documents(id) ON DELETE CASCADE`

Indexes:
- `CREATE INDEX ix_tender_chunks_document_id ON tender_chunks USING btree (document_id)`
- `CREATE UNIQUE INDEX tender_chunks_pkey ON tender_chunks USING btree (id)`

### `tt_failures` (2 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'tt_failures_id_seq'` |
| 2 | `tid` | text | null |  |
| 3 | `url` | text | null |  |
| 4 | `error` | text | null |  |
| 5 | `failed_at` | timestamp with time zone | null | `now()` |

Indexes:
- `CREATE UNIQUE INDEX tt_failures_pkey ON tt_failures USING btree (id)`

### `tt_tender_files` (202 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'tt_tender_files_id_seq'` |
| 2 | `tid` | text | NOT NULL |  |
| 3 | `file_name` | text | NOT NULL |  |
| 4 | `kind` | text | NOT NULL |  |
| 5 | `size` | bigint | null |  |
| 6 | `sha256` | text | null |  |
| 7 | `content` | bytea | null |  |
| 8 | `stored_at` | timestamp with time zone | null | `now()` |

Indexes:
- `CREATE INDEX tt_tender_files_tid_idx ON tt_tender_files USING btree (tid)`
- `CREATE UNIQUE INDEX tt_tender_files_pkey ON tt_tender_files USING btree (id)`
- `CREATE UNIQUE INDEX tt_tender_files_tid_kind_file_name_key ON tt_tender_files USING btree (tid, kind, file_name)`

### `tt_tenders` (38 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'tt_tenders_id_seq'` |
| 2 | `tid` | text | NOT NULL |  |
| 3 | `organization` | text | null |  |
| 4 | `dept_tender_number` | text | null |  |
| 5 | `tender_title` | text | null |  |
| 6 | `product_description` | text | null |  |
| 7 | `key_location` | text | null |  |
| 8 | `tender_type` | text | null |  |
| 9 | `worth` | text | null |  |
| 10 | `emd` | text | null |  |
| 11 | `doc_fees` | text | null |  |
| 12 | `quantity` | text | null |  |
| 13 | `due_date` | date | null |  |
| 14 | `days_to_go` | integer | null |  |
| 15 | `startup_relaxation` | text | null |  |
| 16 | `folder_name` | text | null |  |
| 17 | `path` | text | null |  |
| 18 | `files` | jsonb | null |  |
| 19 | `download_status` | text | null |  |
| 20 | `raw_detail` | text | null |  |
| 21 | `scraped_at` | timestamp with time zone | null | `now()` |
| 22 | `dept_tender_link` | text | null |  |
| 23 | `tender_description` | text | null |  |
| 24 | `department` | text | null |  |
| 25 | `opening_date` | date | null |  |
| 26 | `published_date` | date | null |  |
| 27 | `tender_link` | text | null |  |
| 28 | `files_path` | text | null |  |
| 29 | `zip_path` | text | null |  |
| 30 | `file_count` | integer | null |  |
| 31 | `documents_listed` | jsonb | null |  |
| 32 | `meta_version` | integer | null |  |
| 33 | `first_seen_at` | timestamp with time zone | null | `now()` |
| 34 | `dept_link_type` | text | null |  |
| 35 | `dept_portal_url` | text | null |  |
| 36 | `dept_link_hint` | text | null |  |
| 37 | `files_in_db` | integer | null |  |
| 38 | `worth_amount` | numeric | null |  |
| 39 | `emd_amount` | numeric | null |  |
| 40 | `doc_fee_amount` | numeric | null |  |

Indexes:
- `CREATE INDEX tt_tenders_status_idx ON tt_tenders USING btree (download_status)`
- `CREATE UNIQUE INDEX tt_tenders_pkey ON tt_tenders USING btree (id)`
- `CREATE UNIQUE INDEX tt_tenders_tid_key ON tt_tenders USING btree (tid)`

### `users` (2 rows)

| # | Column | Type | Null | Default |
|---|---|---|---|---|
| 1 | `id` | integer | NOT NULL | `seq 'users_id_seq'` |
| 2 | `email` | character varying(255) | NOT NULL |  |
| 3 | `full_name` | character varying(200) | NOT NULL |  |
| 4 | `hashed_password` | character varying(255) | NOT NULL |  |
| 5 | `is_active` | boolean | NOT NULL |  |
| 6 | `role_id` | integer | NOT NULL |  |
| 7 | `created_at` | timestamp with time zone | NOT NULL |  |
| 8 | `updated_at` | timestamp with time zone | NOT NULL |  |

Foreign keys: `role_id -> roles(id) ON DELETE NO ACTION`

Indexes:
- `CREATE UNIQUE INDEX users_email_key ON users USING btree (email)`
- `CREATE UNIQUE INDEX users_pkey ON users USING btree (id)`
