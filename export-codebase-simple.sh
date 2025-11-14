#!/bin/bash
# Simple codebase export - just the code, no fluff
# Usage: ./export-codebase-simple.sh /path/to/project > knowledge_base/project-name.md

PROJECT_DIR="${1:-.}"
PROJECT_NAME=$(basename "$PROJECT_DIR")

echo "# $PROJECT_NAME"
echo ""

# Project structure
echo "## Structure"
echo '```'
cd "$PROJECT_DIR" && tree -I 'node_modules|__pycache__|*.pyc|.git|venv|env|vendor|dist|build|target' -L 4 2>/dev/null || find . -type f -name "*.py" -o -name "*.js" -o -name "*.go" -o -name "*.rs" | head -20
echo '```'
echo ""

# Include all source files
find "$PROJECT_DIR" -type f \( \
    -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" -o \
    -name "*.go" -o -name "*.rs" -o -name "*.java" -o \
    -name "*.rb" -o -name "*.php" -o -name "*.swift" -o \
    -name "*.kt" -o -name "*.c" -o -name "*.cpp" -o -name "*.h" \
    \) \
    ! -path "*/node_modules/*" \
    ! -path "*/__pycache__/*" \
    ! -path "*/venv/*" \
    ! -path "*/env/*" \
    ! -path "*/.git/*" \
    ! -path "*/vendor/*" \
    ! -path "*/dist/*" \
    ! -path "*/build/*" \
    ! -path "*/target/*" \
    -size -100k \
    | sort \
    | while read file; do

    rel_path="${file#$PROJECT_DIR/}"
    ext="${file##*.}"

    echo "## $rel_path"
    echo ""
    echo '```'"$ext"
    cat "$file"
    echo '```'
    echo ""
done
