ZYNEX - full package (code, database, n8n, downloader)
=====================================================

PRIVATE: this package holds company data and live secrets (see "Secrets inside" below).
Do not upload it, email it outside the company or post it anywhere.

What is in here
---------------
zynex/                     The whole application, as in git (with its .git history):
                             backend/   FastAPI API, AI pipeline, migrations (backend/migrations), seed scripts (backend/scripts)
                             frontend/  React website
                             services/  tender analysis service (port 8001)
                             deploy/    systemd unit, nginx site, backup script, n8n node for automatic analysis
                             docs/      architecture and roadmap
                             backend/uploads/  documents the database points to
                             Xenovex_Technology-KB.xlsx, xenovex_knowledge_base_tender_data.xlsx  company KB source sheets
database/zynex.dump        Full copy of the ZYNEX database (users, company KB, tenders, reports, settings),
                           already at migration 0011 (the latest).
n8n_and_downloader/        Tender Tiger automation:
                             tt_setup_final.sh   installs the Tender Tiger downloader (tt_service) as a service
                             tt_service/         the downloader code (node tt_service.js)
                             workflows/          n8n workflows to import (Tendo = the current server one) and the
                                                 "Send new tenders to ZYNEX" node
setup_new_system.sh        One-time setup on a new Ubuntu machine.

Run on a new machine
--------------------
1. Copy this folder to the machine (Ubuntu 22.04 / 24.04 / 26.04).
2. bash setup_new_system.sh
     installs Python, PostgreSQL, Tesseract and Node, creates database zynex (user zynex / password zynex),
     loads database/zynex.dump, and starts ZYNEX with ./run.
3. Open http://localhost:3000 and log in with your existing ZYNEX accounts (the users come with the database).
   If you forgot a password:  cd zynex/backend && .venv/bin/python -m scripts.manage_users set-password --email <email>
4. In Settings, check the AI address (Ollama / NVIDIA), document storage and the Teams webhook: they point to
   the office machines (e.g. Ollama 192.168.10.154, file server 10.10.10.19).

Next times: cd zynex && ./run

./run creates backend/.env with the local database (zynex/zynex@localhost:5432/zynex) when it is missing.
The office .env files are NOT included, so the package never points at the office database by itself.

Tender Tiger downloader and n8n (optional)
------------------------------------------
1. Downloader:  cd n8n_and_downloader && bash tt_setup_final.sh   (asks for its settings, creates service.env)
2. n8n:         docker run -d --name n8n -p 5678:5678 -v ~/.n8n:/home/node/.n8n \
                  -v $HOME/Tendo_Docs:$HOME/Tendo_Docs -e N8N_RESTRICT_FILE_ACCESS_TO=$HOME/Tendo_Docs \
                  -e NODE_FUNCTION_ALLOW_BUILTIN=fs n8nio/n8n
                then open http://localhost:5678 > Import from file > workflows/Tendo (current server workflow).json
3. Automatic analysis: make the n8n account (password 12+ characters) and its token
                  cd zynex/backend
                  .venv/bin/python -m scripts.manage_users create --email n8n@zynex.local --name "n8n automation" --role analyst
                  .venv/bin/python -m scripts.automation_token --email n8n@zynex.local
                put it in the "Send new tenders to ZYNEX" node, and turn on Settings > Tender Analysis > Auto analyse.

Secrets inside
--------------
- database: settings hold the NVIDIA API key, Teams webhook and file-server login; user password hashes.
- workflows/Tendo*.json: Tender Tiger login, downloader token, Teams webhook.
Change these after moving if the package ever leaves your hands.
