#!/bin/bash
# Create cache directories with correct permissions before first run
# Also cleans stale lock files that can cause container hangs
# Run this once: ./scripts/setup-cache.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Creating cache directories in $PROJECT_DIR/.cache/"

mkdir -p "$PROJECT_DIR/.cache/huggingface/hub"
mkdir -p "$PROJECT_DIR/.cache/docling"
mkdir -p "$PROJECT_DIR/.cache/easyocr"
mkdir -p "$PROJECT_DIR/.cache/clamav"
mkdir -p "$PROJECT_DIR/.cache/deepsearch_glm"
mkdir -p "$PROJECT_DIR/.cache/rapidocr"
mkdir -p "$PROJECT_DIR/.cache/query_expansion"
mkdir -p "$PROJECT_DIR/.cache/ollama"

echo "Cleaning stale lock files..."

# Clean stale lock files from all model caches (can cause container hangs)
find "$PROJECT_DIR/.cache/huggingface" -name "*.lock" -delete 2>/dev/null || true
find "$PROJECT_DIR/.cache/docling" -name "*.lock" -delete 2>/dev/null || true
find "$PROJECT_DIR/.cache/easyocr" -name "*.lock" -delete 2>/dev/null || true
find "$PROJECT_DIR/.cache/deepsearch_glm" -name "*.lock" -delete 2>/dev/null || true

echo "Cache directories created and cleaned successfully."
echo "You can now run: docker-compose up -d"
