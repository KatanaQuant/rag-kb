#!/bin/bash
# Export codebase with context for reverse engineering and comparison
# Usage: ./export-for-analysis.sh /path/to/project "Brief description" > knowledge_base/project-analysis.md

PROJECT_DIR="${1:-.}"
DESCRIPTION="${2:-No description provided}"
PROJECT_NAME=$(basename "$PROJECT_DIR")
TIMESTAMP=$(date '+%Y-%m-%d')

cat <<EOF
# Code Analysis: $PROJECT_NAME

**Date:** $TIMESTAMP
**Purpose:** $DESCRIPTION
**Location:** $PROJECT_DIR

---

## Executive Summary

### Project Intent
<!-- What is this codebase trying to accomplish? -->
$DESCRIPTION

### Key Design Patterns Used
<!-- Auto-detected or add manually -->
- [ ] To be analyzed

### Dependencies on Other Projects
<!-- Does this relate to other codebases you're analyzing? -->
- [ ] To be documented

---

## Architecture Overview

### Directory Structure
\`\`\`
EOF

cd "$PROJECT_DIR" && tree -I 'node_modules|__pycache__|*.pyc|.git|venv|env|vendor|dist|build' -L 3 2>/dev/null || ls -R

cat <<EOF
\`\`\`

### Entry Points
<!-- Main files where execution starts -->

EOF

# Find likely entry points
find "$PROJECT_DIR" -maxdepth 2 -type f \( -name "main.py" -o -name "app.py" -o -name "index.js" -o -name "main.go" -o -name "server.py" \) 2>/dev/null | while read entry; do
    rel_path="${entry#$PROJECT_DIR/}"
    echo "- \`$rel_path\`"
done

cat <<EOF

---

## Core Implementation

EOF

# Export key files with context
find "$PROJECT_DIR" -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.go" -o -name "*.rs" -o -name "*.rb" \) \
    ! -path "*/node_modules/*" \
    ! -path "*/__pycache__/*" \
    ! -path "*/venv/*" \
    ! -path "*/.git/*" \
    ! -path "*/vendor/*" \
    ! -path "*/dist/*" \
    ! -path "*/build/*" \
    ! -path "*test*" \
    -size -50k \
    | head -30 \
    | while read file; do

    rel_path="${file#$PROJECT_DIR/}"
    ext="${file##*.}"
    lines=$(wc -l < "$file")

    # Extract class names for better context
    classes=$(grep -E "^class |^interface |^struct |^type " "$file" 2>/dev/null | head -5 | sed 's/[:{].*//')

    echo "### File: \`$rel_path\`"
    echo ""
    echo "**Lines:** $lines"

    if [ -n "$classes" ]; then
        echo "**Defines:**"
        echo "$classes" | while read line; do
            echo "- $line"
        done
    fi

    echo ""
    echo "\`\`\`$ext"
    cat "$file"
    echo "\`\`\`"
    echo ""
    echo "**Analysis Notes:**"
    echo "<!-- Add your observations about this file -->"
    echo "- Pattern used: "
    echo "- Similar to (book/project): "
    echo "- Potential issues: "
    echo ""
    echo "---"
    echo ""
done

cat <<EOF

## Cross-Reference Checklist

### Design Patterns to Verify
- [ ] Does class design follow Single Responsibility Principle?
- [ ] Are dependencies injected properly?
- [ ] Is inheritance used appropriately vs composition?
- [ ] Are code smells present? (God objects, long methods, etc.)

### Compare to Books
- [ ] Sandi Metz's POODR principles
- [ ] 99 Bottles refactoring techniques
- [ ] Martin Kleppmann's data system patterns

### Compare to Other Projects
- [ ] Similar to project: _______
- [ ] Differences: _______
- [ ] Improvements over previous version: _______

### Regression Check
- [ ] Known issues from other projects present here?
- [ ] Previous bug fixes applied?
- [ ] Performance patterns improved?

---

## Lessons Learned

### What Works Well
<!-- Document good patterns to reuse -->

### What Could Be Improved
<!-- Document anti-patterns or technical debt -->

### Migration Notes
<!-- If refactoring, document the process -->

---

**Generated:** $TIMESTAMP
**Tool:** export-for-analysis.sh
EOF
