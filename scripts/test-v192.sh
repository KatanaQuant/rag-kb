#!/bin/bash
# Test script for v1.9.2 backport in isolated environment
#
# This script:
# 1. Reuses existing SQLite database (data/rag.db with ~50k vectors)
# 2. Mounts empty KB dir so nothing gets indexed
# 3. Pauses indexing immediately after startup
# 4. Tests search performance (should be ~2s, not 20s)
# 5. Does NOT affect running v2 instance (different port, read-only DB access)

set -e

echo "=== v1.9.2 Isolated Test ==="
echo "Reusing existing SQLite database with ~50k vectors"
echo "v2 instance on port 8000 will NOT be affected"
echo ""

# Paths
PROJECT_DIR="/media/veracrypt1/CODE/rag-kb"
KB_EMPTY="${PROJECT_DIR}/kb-empty"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.v192-test.yml"
API_URL="http://localhost:8001"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[v1.9.2-test]${NC} $1"; }
warn() { echo -e "${YELLOW}[v1.9.2-test]${NC} $1"; }
error() { echo -e "${RED}[v1.9.2-test]${NC} $1"; }

# 1. Verify existing database
if [ ! -f "${PROJECT_DIR}/data/rag.db" ]; then
    error "No existing database at ${PROJECT_DIR}/data/rag.db"
    exit 1
fi
log "Found existing database: $(ls -lh ${PROJECT_DIR}/data/rag.db | awk '{print $5}')"

# 2. Create empty KB directory
log "Creating empty KB directory..."
mkdir -p "${KB_EMPTY}"

# 3. Build container
log "Building v1.9.2 container..."
cd "${PROJECT_DIR}"
docker-compose -f "${COMPOSE_FILE}" build

# 4. Start container
log "Starting v1.9.2 container..."
docker-compose -f "${COMPOSE_FILE}" up -d

# 5. Wait for health (will take ~42s to load vectors into memory)
log "Waiting for API to be healthy (~42s to load vectors into memory)..."
for i in {1..120}; do
    if curl -s "${API_URL}/health" > /dev/null 2>&1; then
        log "API is healthy!"
        break
    fi
    if [ $i -eq 120 ]; then
        error "Timeout waiting for API"
        docker-compose -f "${COMPOSE_FILE}" logs --tail=50
        exit 1
    fi
    echo -n "."
    sleep 1
done
echo ""

# 6. IMMEDIATELY pause indexing
log "Pausing indexing to prevent any processing..."
pause_result=$(curl -s -X POST "${API_URL}/indexing/pause" 2>/dev/null)
echo "$pause_result" | python3 -m json.tool 2>/dev/null || echo "$pause_result"

# 7. Show stats
log "Database stats:"
curl -s "${API_URL}/indexing/status" | python3 -m json.tool 2>/dev/null || curl -s "${API_URL}/indexing/status"

echo ""
log "=== Test Environment Ready ==="
echo "  API URL:    ${API_URL}"
echo "  Container:  rag-api-v192-test"
echo "  Database:   ${PROJECT_DIR}/data/rag.db (reused)"
echo ""
echo "Test search performance (should be ~2s, not 20s):"
echo ""
echo "  time curl -s -X POST ${API_URL}/query \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"machine learning\", \"top_k\": 5}'"
echo ""
echo "Other commands:"
echo "  Logs:    docker-compose -f ${COMPOSE_FILE} logs -f"
echo "  Stop:    docker-compose -f ${COMPOSE_FILE} down"
