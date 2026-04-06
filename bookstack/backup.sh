#!/bin/bash
# BookStack daily backup script
# Add to crontab: 0 2 * * * /home/guogaoliang/bookstack/backup.sh

set -euo pipefail

BACKUP_DIR="/home/guogaoliang/bookstack/backups"
DATE=$(date +%Y%m%d_%H%M)
COMPOSE_DIR="/home/guogaoliang/bookstack"

mkdir -p "$BACKUP_DIR"

# Load env for DB password
source "$COMPOSE_DIR/.env"

# Backup MySQL
echo "[$(date)] Backing up database..."
docker exec bookstack_db mysqldump -u bookstack -p"${DB_PASS}" bookstackapp > "$BACKUP_DIR/db_${DATE}.sql"

# Backup uploaded files
echo "[$(date)] Backing up uploads..."
tar -czf "$BACKUP_DIR/uploads_${DATE}.tar.gz" -C "$COMPOSE_DIR/bookstack_data/www" uploads/ 2>/dev/null || echo "No uploads to backup"

# Backup ranking data
echo "[$(date)] Backing up ranking data..."
cp "$COMPOSE_DIR/ranking_data/ranking.db" "$BACKUP_DIR/ranking_${DATE}.db" 2>/dev/null || echo "No ranking DB yet"

# Cleanup: keep 30 days
find "$BACKUP_DIR" -name "db_*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "uploads_*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "ranking_*.db" -mtime +30 -delete

echo "[$(date)] Backup complete: $BACKUP_DIR"
