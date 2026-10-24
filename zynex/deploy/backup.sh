#!/usr/bin/env bash
# Nightly backup of everything that cannot be rebuilt: the database and the uploaded documents.
# Usage:  sudo -u zynex /opt/zynex/deploy/backup.sh
# Cron :  0 2 * * *  zynex  /opt/zynex/deploy/backup.sh >> /var/log/zynex-backup.log 2>&1
#
# Reads the database connection from backend/.env (DATABASE_URL). Keeps the newest $KEEP_DAYS days.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/zynex}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/zynex}"
KEEP_DAYS="${KEEP_DAYS:-14}"

env_value() { grep -E "^$1=" "$APP_DIR/backend/.env" | head -1 | cut -d= -f2-; }

DB_URL="$(env_value DATABASE_URL)"
UPLOAD_DIR="$(env_value UPLOAD_DIR)"
[ -n "$DB_URL" ] || { echo "DATABASE_URL not found in $APP_DIR/backend/.env" >&2; exit 1; }
UPLOAD_DIR="${UPLOAD_DIR:-/var/lib/zynex/uploads}"

# pg_dump wants a plain postgresql:// URL, not the SQLAlchemy driver form
PG_URL="${DB_URL/postgresql+asyncpg:/postgresql:}"

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
pg_dump --format=custom --file="$BACKUP_DIR/zynex-db-$STAMP.dump" "$PG_URL"
tar -C "$(dirname "$UPLOAD_DIR")" -czf "$BACKUP_DIR/zynex-uploads-$STAMP.tar.gz" "$(basename "$UPLOAD_DIR")"

find "$BACKUP_DIR" -name 'zynex-*' -mtime +"$KEEP_DAYS" -delete
echo "$(date -Is) backup ok: $BACKUP_DIR/zynex-db-$STAMP.dump"

# Restore (stop the API first):
#   pg_restore --clean --if-exists --dbname="$PG_URL" zynex-db-<stamp>.dump
#   tar -C /var/lib/zynex -xzf zynex-uploads-<stamp>.tar.gz
