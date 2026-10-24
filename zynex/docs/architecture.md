# Architecture

## Layers (backend)

```
api/v1/*        HTTP routes: authentication, role checks, request/response shapes
services/*      business logic with no AI calls (parsing stages, rule engine, verdict, report PDF)
ai/*            everything that talks to a model: llm_client (provider switch), prompts, extraction, reasoning
models/*        SQLAlchemy tables           schemas/*   Pydantic shapes shared by services
parsers/*       PDF / DOCX / TXT text extraction (PyMuPDF, python-docx; pure Python)
exporters/*     DOCX / PDF output           core/*      config, security, settings registry, database
```

Rule of thumb: services never import from `ai/`; the AI layer is handed to them (see `EligibilityPipeline`, which
receives the extractor and the explainer as arguments), so the whole flow is testable without a model.
Some older routes (estimation, proposals) still mix logic into the route file; see the roadmap.

## Configuration

`app.core.config.settings` answers `settings.X` from layers, first match wins:
test override > value saved on the Settings page (`app_settings` table) > default in `settings_registry.py` > env field.
Bootstrap values (`DATABASE_URL`, `SECRET_KEY`, `ENVIRONMENT`, `UPLOAD_DIR`, `CORS_ORIGINS`, `NVIDIA_API_KEY`) come from
`backend/.env` only. Nothing reads a setting once and caches it: model address, thresholds and concurrency are looked up
at the moment of use, so a change on the Settings page applies without a restart. A background task refreshes the
saved values every 15 s so several worker processes would converge.

To add a setting: add a `SettingDef` to `settings_registry.py` (it appears on the Settings page through the generic
form) and read it as `settings.<ATTR>`.

## Database

PostgreSQL only. The schema is owned by Alembic: `alembic upgrade head`. The API never creates or alters tables.
Create a migration after changing a model: `alembic revision --autogenerate -m "what changed"`, review it, commit it.
`alembic check` reports drift between the models and the database.
Embeddings are stored as text and compared in Python (no vector extension needed); fine for thousands of passages,
revisit if the corpus grows large.

## Tender analysis pipeline

`POST /api/v1/tender/upload` validates the file and starts a background run; screens poll `/status` and read `/report`.

1. **S1** validate (type, size, "is this a tender?" check)  **S2** extract text (PDF/DOCX/TXT; OCR for scanned pages)
2. **S3** detect structure  **S4** split into page chunks
3. **S5** locate the eligibility section (heading or eligibility table, followed across page breaks and trimmed to
   the section); a few strongly eligibility-looking pages elsewhere are read too. The stage output lists the pages
   read and any page that looks like eligibility text but was not read. If the located section yields no criteria,
   the best-scoring other pages are read instead, so a run never ends with an empty checklist
4. **S6** the model extracts criteria (table rows one by one, prose page by page; JSON constrained, retried on
   malformed output). Mis-filed fields, empty values and invented numbers are removed
5. **S7** every quote must be found in the tender text (fuzzy match, every number must match exactly, also across a
   page break); a quote that does not speak about its field is moved to manual review; repeated clauses collapse.
   Unverified criteria can never produce a PASS or FAIL
6. **S8** each requirement is aligned with the company records: which entity answers it, the requirement in
   canonical form (rupees, years, financial-year window, certificate names), and the company projects whose
   description matches the kind of work asked for
7. **S9** rule engine compares criteria with the company's records (certifications, financial records, projects,
   employees, technologies). Missing data is reported as MISSING; nothing is assumed
8. **S10** verdict (eligible / partial / not eligible), action checklist, and an AI-written reasoning for every
   item (checked against the item's own facts; the rule-based wording is used when the model's text is not faithful).
   Documents to hand in are a to-do list and do not keep an otherwise eligible bidder at PARTIAL

The run (criteria, per-stage output, metrics, the model used) is stored on `eligibility_reports`.

## Security model

JWT login, roles `admin` / `analyst` / `viewer`. Viewers are read-only on every router; the knowledge base and Settings
are writable by administrators only. There is no default account: users are created with `scripts/manage_users.py`.
Secrets stay in `backend/.env`; the Settings page never stores or shows them.

## Frontend

React + TypeScript + Tailwind. `src/pages` per role area, `src/api` one module per backend area, `src/store` for
auth and the local copy of server settings. The tender screens (`src/features/tender`) use their own stylesheet
scoped under `.tender-scope`.
