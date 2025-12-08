#!/bin/bash
# Export PostgreSQL database to data/ragkb_backup.sql
# Usage: ./scripts/backup_postgres.sh [--compress]

set -e

BACKUP_FILE="data/ragkb_backup.sql"
COMPRESS=false

if [[ "$1" == "--compress" ]]; then
    COMPRESS=true
fi

echo "Exporting PostgreSQL database..."

# Use --clean to generate DROP statements (allows re-import over existing data)
docker exec rag-kb-postgres pg_dump -U ragkb --clean --if-exists ragkb > "$BACKUP_FILE"

if [[ "$COMPRESS" == true ]]; then
    echo "Compressing backup..."
    gzip -f "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE}.gz"
fi

SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "Backup complete: $BACKUP_FILE ($SIZE)"
