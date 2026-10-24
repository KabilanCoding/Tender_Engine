#!/usr/bin/env bash
# One-time setup of ZYNEX on a new Ubuntu machine, then start it.
#   bash setup_new_system.sh
# After this, start ZYNEX any time with:  cd zynex && ./run
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== 1/4  System packages (Python, PostgreSQL, OCR, PDF libraries) =="
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential libpq-dev \
                    postgresql postgresql-client tesseract-ocr libpango-1.0-0 libpangoft2-1.0-0 curl

if ! command -v node >/dev/null || [ "$(node -v | cut -c2- | cut -d. -f1)" -lt 20 ]; then
  echo "== Node 20+ is needed for the website. Installing Node 22 with nvm =="
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"
  nvm install 22
fi

echo "== 2/4  Database: user zynex / password zynex, database zynex =="
sudo systemctl enable --now postgresql
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='zynex'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE ROLE zynex LOGIN PASSWORD 'zynex' CREATEDB;"
if sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='zynex'" | grep -q 1; then
  echo "Database zynex already exists: not restoring over it."
else
  sudo -u postgres psql -c "CREATE DATABASE zynex OWNER zynex;"
  echo "== 3/4  Loading the saved data (database/zynex.dump) =="
  PGPASSWORD=zynex pg_restore -h localhost -U zynex -d zynex --no-owner --no-privileges "$HERE/database/zynex.dump" \
    || echo "(some restore warnings above are normal)"
fi

echo "== 4/4  Starting ZYNEX (installs Python and website packages on the first run) =="
cd "$HERE/zynex"
chmod +x run
./run
