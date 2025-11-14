#!/bin/bash
# Export codebase to markdown for RAG ingestion
# Usage: ./export-codebase.sh /path/to/project > knowledge_base/project-code.md

PROJECT_DIR="${1:-.}"
PROJECT_NAME=$(basename "$PROJECT_DIR")

echo "# Codebase: $PROJECT_NAME"
echo ""
echo "Generated: $(date)"
echo ""

# Project structure
echo "## Project Structure"
echo '```'
cd "$PROJECT_DIR" && tree -I 'node_modules|__pycache__|*.pyc|.git|venv|env' -L 3 || ls -R
echo '```'
echo ""

# Find and include source files
find "$PROJECT_DIR" -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.go" -o -name "*.rs" -o -name "*.java" \) \
    ! -path "*/node_modules/*" \
    ! -path "*/__pycache__/*" \
    ! -path "*/venv/*" \
    ! -path "*/.git/*" \
    | while read file; do

    rel_path="${file#$PROJECT_DIR/}"

    echo "## File: $rel_path"
    echo ""
    echo '```'$(basename "$file" | sed 's/.*\.//')
    cat "$file"
    echo '```'
    echo ""
done

echo "---"
echo "End of codebase export"
