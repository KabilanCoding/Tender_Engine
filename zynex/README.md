# ZYNEX

**Z**ero-Cloud, **Y**our-Data, **N**eural **E**stimation & e**X**ecution: a local AI platform that reads requirement
documents and tenders, estimates projects and cost, checks tender eligibility against the company's own records, and
produces proposal documents. Models run on your own server (Ollama); no data leaves the machine.

| Part | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 (async), Alembic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | PostgreSQL |
| AI | Ollama (local models), PyMuPDF + Tesseract for documents |

## Repository layout

```
backend/     FastAPI application
  app/         api/ (routes)  services/ (business logic)  ai/ (everything that talks to a model)
               models/ (database tables)  schemas/  parsers/  exporters/  core/ (config, security, settings)
  migrations/  Alembic database migrations (the only way tables are created or changed)
  scripts/     command-line tools: users, cost-rate seed, demo data (dev only)
  tests/       pytest suite and fixtures
frontend/    React web app (src/features/tender = the tender analysis screens)
deploy/      server installation: systemd unit, nginx site, backup script, step-by-step guide
docs/        architecture, roadmap
```

## Run it locally (development)

You need Python 3.11+, Node 20+, PostgreSQL and [Ollama](https://ollama.com) with at least one model pulled
(`ollama pull qwen2.5:14b`, `ollama pull bge-m3` for the company-data search; without it the search falls back to keywords).

**Fastest way: `./run`** (Linux/macOS). With PostgreSQL running and an empty database and login `zynex` / `zynex` created
(see below), it creates the Python environment, installs the frontend, writes `backend/.env` for development, applies every
migration, seeds demo data, and starts the three processes:

| Process | Address |
|---|---|
| Core backend (login, knowledge base, estimation, proposals, settings) | http://localhost:8000 |
| Tender analysis service (upload, analysis, reports, Tender Tiger) | http://localhost:8001 |
| Web app (proxies `/api` to the two services) | http://localhost:3000 |

On the **first run** it prints a development login once: `admin@zynex.local` and a random password (change it with
`python -m scripts.manage_users set-password --email admin@zynex.local`). It also loads a **fictional** demo company
("Demo Technologies") so a tender check has company records to compare with. Both steps do nothing on later runs and never
touch real data.

```bash
# database, once:  CREATE ROLE zynex LOGIN PASSWORD 'zynex';  CREATE DATABASE zynex OWNER zynex;
./run
```

Manual steps (what `./run` does), if you prefer:

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt     # Windows: .venv\Scripts\pip
cp .env.example .env                  # set ENVIRONMENT=development, DATABASE_URL, SECRET_KEY
.venv/bin/alembic upgrade head        # create the tables (migrations 0001-0007)
.venv/bin/python -m scripts.manage_users init-roles
.venv/bin/python -m scripts.manage_users ensure-dev-admin        # or: create --email you@local --name "You" --role admin
.venv/bin/python -m scripts.seed_demo_data && .venv/bin/python -m scripts.seed_demo_company   # optional, fictional
.venv/bin/uvicorn main:app --reload --port 8000
cd ../services/tender_service && ../../backend/.venv/bin/uvicorn main:app --reload --port 8001
cd ../../frontend && npm install && npm run dev                  # http://localhost:3000
```

The tender service does not keep its own copy of the analysis code: its `app/` folders are links into `backend/app`
(see `services/tender_service/README.md`), so a fix is made once.

Log in, open **Settings > AI Model** and choose the model; **Settings > Tender analysis** has the full-checklist and
(temporary) step-by-step trace switches. Company data can be loaded from a workbook with
`python -m scripts.import_company_kb <file.xlsx> --apply` (see `docs/company-knowledge-base.md`; workbooks are never committed).

Tests: `cd backend && pytest`. Type check the frontend: `cd frontend && npx tsc --noEmit`.

## Configuration

Two layers, on purpose:

- **`backend/.env`**: only what the server needs before it can reach the database (environment, `DATABASE_URL`,
  `SECRET_KEY`, upload folder, allowed origin). See `backend/.env.example`.
- **Settings page** (administrators): everything else, saved in the database and applied immediately: AI provider and
  model, context and output limits, tender-analysis thresholds, search options, prompts, upload limits.
  The definitions live in `backend/app/core/settings_registry.py`.

## Deploying

See [deploy/README.md](deploy/README.md). Architecture and design notes: [docs/architecture.md](docs/architecture.md).
Open work: [docs/ROADMAP.md](docs/ROADMAP.md).
