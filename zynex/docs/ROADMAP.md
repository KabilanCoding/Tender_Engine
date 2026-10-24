# Roadmap

Open work, most important first. Items marked **before wider rollout** are known gaps in the current release.

## Reliability and scale
- **Before wider rollout: durable analysis jobs.** Runs execute inside the API process and their live progress is held in
  memory, so the API runs with one worker and a restart interrupts a running analysis. Move job state and progress to the
  database (or a small queue) so restarts resume or fail cleanly and more than one worker can run.
- Long tenders are slow on a local 14B model (about 20 min for 88 pages). Ideas: smaller first-pass model, overlap
  extraction and explanation, GPU with more memory.
- Embedding search compares vectors in Python. Add pgvector (or an index) when the document corpus grows beyond a few
  thousand passages.

## Tender analysis quality
- **Before wider rollout: measure the pre-filter.** It is a vocabulary heuristic; build a few hand-labelled tenders and
  check recall (`ELIGIBILITY_PREFILTER` can be switched off on the Settings page).
- Grounding proves a quote exists in the tender, not that it supports the extracted value. Add a check that the value
  or key terms appear in the quote and drop heading-only quotes.
- Rule engine: periods ("last N financial years"), N-of-M rules, certificate validity on the bid date, role
  experience for key personnel, consortium rules.
- Evaluation harness: labelled tenders, precision/recall per run, run before changing models or prompts.
- Legacy `.doc` input (only PDF, DOCX and TXT today).

## Knowledge base
- **Before wider rollout: financial records screen** (the table and rule exist, there is no UI/API to enter turnover).
- Facts the rules need but the knowledge base does not hold: net worth, years in business, blacklisting status,
  registrations (GST, PAN, MSME), office locations, key personnel with qualifications and experience.
- Per-fact evidence (document, date, who confirmed) so a PASS can cite its source.

## Product and security
- **Before wider rollout: user management in the app** (today: `scripts/manage_users.py`), password change, login
  attempt limiting.
- Per-user ownership and an audit log (who uploaded, ran, changed settings). `uploaded_by` is recorded; reports are
  visible to every logged-in user.
- Settings are global; add per-user preferences only if needed.
- Role checks are enforced per router; add automated tests that assert every route requires the intended role.

## Code structure
- Move business logic out of route files (estimation, proposals, knowledge base) into `services/`, matching the tender
  module, and add tests around it.
- Frontend: split the large pages (project estimation, knowledge base) and add component tests for the tender screens.
- CI: run `pytest`, `alembic check` against an empty database, and the frontend type check on every change.
