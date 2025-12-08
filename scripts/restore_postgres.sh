#!/bin/bash
# Import PostgreSQL database from data/ragkb_backup.sql
# Works for fresh installs AND incremental updates (replaces existing data)
# Usage: ./scripts/restore_postgres.sh [backup_file]

set -e

BACKUP_FILE="${1:-data/ragkb_backup.sql}"

# Handle compressed files
if [[ "$BACKUP_FILE" == *.gz ]]; then
    echo "Decompressing backup..."
    gunzip -k "$BACKUP_FILE"
    BACKUP_FILE="${BACKUP_FILE%.gz}"
fi

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Check if postgres is running
if ! docker exec rag-kb-postgres pg_isready -U ragkb -q 2>/dev/null; then
    echo "Starting PostgreSQL..."
    docker-compose up -d postgres
    echo "Waiting for PostgreSQL to be ready..."
    sleep 10
fi

echo "Importing database from $BACKUP_FILE..."
echo "(This will replace existing data if any)"

# Import - the --clean flag in pg_dump means DROP statements are included
docker exec -i rag-kb-postgres psql -U ragkb ragkb < "$BACKUP_FILE"

# Verify
DOC_COUNT=$(docker exec rag-kb-postgres psql -U ragkb ragkb -t -c "SELECT COUNT(*) FROM documents;" | tr -d ' ')
CHUNK_COUNT=$(docker exec rag-kb-postgres psql -U ragkb ragkb -t -c "SELECT COUNT(*) FROM chunks;" | tr -d ' ')
VEC_COUNT=$(docker exec rag-kb-postgres psql -U ragkb ragkb -t -c "SELECT COUNT(*) FROM vec_chunks;" | tr -d ' ')

echo ""
echo "Import complete!"
echo "  Documents: $DOC_COUNT"
echo "  Chunks:    $CHUNK_COUNT"
echo "  Vectors:   $VEC_COUNT"
echo ""
echo "Start full stack: docker-compose up -d"
