# Deploying ZYNEX on a Linux server

ZYNEX is three processes on one machine: **PostgreSQL** (data), the **API** (FastAPI, run by systemd) and
**nginx** (serves the web app and forwards `/api`). The AI runs in **Ollama** on the same machine. Nothing else
is required: no Docker, Java or graph database. Written for Ubuntu 22.04/24.04; other distributions need the
equivalent packages.

```
 browser ──https──> nginx ──/──> static web app (/var/www/zynex)
                       └──/api──> API 127.0.0.1:8000 ──> PostgreSQL
                                          └──────────> Ollama 127.0.0.1:11434 (local models)
```

## 1. Prerequisites

| Need | Notes |
|---|---|
| Python 3.11 or 3.12 | for the API |
| PostgreSQL 14+ | an empty database and a login for ZYNEX (plain PostgreSQL; no extensions) |
| nginx | web server |
| Ollama | runs the AI models locally; GPU strongly recommended |
| `tesseract-ocr`, `libpango-1.0-0`, `libpangoft2-1.0-0` | OCR for scanned tenders, PDF proposals |
| Node 20 + npm | only to **build** the web app; build on any machine and copy `dist/` if the server has no Node |

```bash
sudo apt install python3 python3-venv python3-dev build-essential libpq-dev nginx \
                 tesseract-ocr libpango-1.0-0 libpangoft2-1.0-0 postgresql-client
```

Scanned tenders in Indian languages need the matching Tesseract language packs. Install the ones you expect
(Hindi, Marathi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Punjabi, Odia, Urdu shown):

```bash
sudo apt install tesseract-ocr-osd tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-tam tesseract-ocr-tel \
                 tesseract-ocr-kan tesseract-ocr-mal tesseract-ocr-ben tesseract-ocr-guj tesseract-ocr-pan \
                 tesseract-ocr-ori tesseract-ocr-urd
```

Each scanned page is read with English plus the language of its script. If a page reads badly, the other installed
Indian languages are tried, and a page that still reads badly is flagged on the run. A language that is configured
but not installed is reported on the run too. Without root access, put the `*.traineddata` files (from the
`tessdata_fast` project) in a folder, include `eng.traineddata` and `osd.traineddata`, and set it under
**Settings > Tender Analysis > Extra OCR language folder**. `OCR languages` on the same page limits the languages used.

## 2. Database

Create the database once (names are examples):

```sql
CREATE ROLE zynex LOGIN PASSWORD 'choose-a-strong-password';
CREATE DATABASE zynex OWNER zynex;
```

## 3. Install the application

```bash
sudo useradd --system --create-home --home-dir /opt/zynex --shell /usr/sbin/nologin zynex
sudo mkdir -p /var/lib/zynex/uploads && sudo chown -R zynex:zynex /var/lib/zynex
# copy the repository to /opt/zynex (git clone, or unpack a release), then:
sudo -u zynex python3 -m venv /opt/zynex/backend/.venv
sudo -u zynex /opt/zynex/backend/.venv/bin/pip install -r /opt/zynex/backend/requirements.txt
```

## 4. Configure

```bash
sudo -u zynex cp /opt/zynex/backend/.env.example /opt/zynex/backend/.env
sudo -u zynex nano /opt/zynex/backend/.env
```

Only five values live in this file (everything else is changed later on the **Settings** page):
`ENVIRONMENT=production`, `DATABASE_URL`, `SECRET_KEY` (generate with
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`), `UPLOAD_DIR`, `CORS_ORIGINS`.
In production the API refuses to start with a weak secret or the development database URL.
Keep this file readable only by the service user: `chmod 600 backend/.env`.

## 5. Create the schema and the first administrator

```bash
cd /opt/zynex/backend
sudo -u zynex .venv/bin/alembic upgrade head                       # creates all tables
sudo -u zynex .venv/bin/python -m scripts.manage_users init-roles
sudo -u zynex .venv/bin/python -m scripts.manage_users create --email you@company.com --name "Your Name" --role admin
sudo -u zynex .venv/bin/python -m scripts.seed_cost_parameters     # optional: starting hourly rates (editable in the app)
```

There is no default account. More users: the same `create` command with `--role analyst` or `viewer`.

## 6. AI models (Ollama)

```bash
curl -fsSL https://ollama.com/install.sh | sh        # on an offline server: install from a downloaded package
ollama pull nomic-embed-text                          # embeddings for document search
ollama pull qwen2.5:14b                               # recommended for tender analysis (needs about 10 GB of GPU/CPU memory)
```

Offline server: run the `pull` commands on a connected machine and copy its `~/.ollama/models` folder to
the server's Ollama model directory. Then log in to ZYNEX as administrator, open **Settings > AI Model** and
choose the default model. Tenders cannot be analysed until a model is selected.

## 7. Build and publish the web app

```bash
cd /opt/zynex/frontend && npm ci && npm run build          # or build elsewhere and copy dist/
sudo mkdir -p /var/www/zynex && sudo rsync -a --delete dist/ /var/www/zynex/
```

## 8. Start everything

```bash
sudo cp /opt/zynex/deploy/zynex-backend.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now zynex-backend

sudo cp /opt/zynex/deploy/nginx-zynex.conf /etc/nginx/sites-available/zynex     # edit server_name first
sudo ln -sf /etc/nginx/sites-available/zynex /etc/nginx/sites-enabled/zynex
sudo nginx -t && sudo systemctl reload nginx
```

Check it: `curl http://127.0.0.1:8000/health/ready` should return `"status":"ok"` with the database and AI both `ok`.
Then open the site, log in, and visit **Settings** (pick the model) and **Knowledge Base** (add certifications,
projects, financial records) before analysing tenders: with an empty knowledge base every criterion is reported
as "Missing data".

## Operations

**Backups** (database + uploaded files): schedule `deploy/backup.sh` nightly (instructions inside the script).
When Settings > System > Document storage is "file server", the documents live in that server's folder
(e.g. `/home/xenovex/Tendo_Docs/ZYNEX`); back that folder up on the file server as well.
Test a restore on a spare machine before relying on it.

**Upgrade**
```bash
cd /opt/zynex && git pull                                  # or unpack the new release
sudo -u zynex backend/.venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build && sudo rsync -a --delete dist/ /var/www/zynex/)
sudo systemctl restart zynex-backend                       # runs pending migrations before starting
```
Do not restart while a tender is being analysed: running analyses stop with the process (start them again).

**Logs**: `journalctl -u zynex-backend -f` (API), `/var/log/nginx/error.log` (web).

**Change the model, thresholds, limits, prompts**: Settings page, no restart needed.

**Rotate the secret key**: edit `SECRET_KEY`, restart; everyone must log in again.

**Troubleshooting**
| Symptom | Check |
|---|---|
| Login works, AI features say "No AI model is selected" | Settings > AI Model |
| Analysis fails on every page | `ollama list` shows the chosen model; `curl localhost:11434`; GPU memory |
| Uploads rejected | `client_max_body_size` in nginx and "Max upload size" in Settings |
| 502 from nginx | `systemctl status zynex-backend`; usually a wrong `DATABASE_URL` |
| API will not start in production | the message names the unsafe setting (weak `SECRET_KEY`, development database) |

## Known limits of this release

- One API worker only (live progress of running analyses is held in memory). Fine for a team; see `docs/ROADMAP.md`.
- Long analyses run inside the API process: a restart interrupts them.
- Settings and the knowledge base are shared by all users of the server.
