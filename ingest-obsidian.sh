#!/bin/bash
# Ingest Obsidian vault into RAG knowledge base
# Usage: ./ingest-obsidian.sh /path/to/vault [output-name]

set -e

VAULT_PATH="$1"
OUTPUT_NAME="${2:-obsidian-vault}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$VAULT_PATH" ]; then
    echo -e "${RED}Error: Vault path required${NC}"
    echo "Usage: $0 /path/to/vault [output-name]"
    echo ""
    echo "Example:"
    echo "  $0 ~/Documents/MyVault obsidian-notes"
    exit 1
fi

if [ ! -d "$VAULT_PATH" ]; then
    echo -e "${RED}Error: Vault path does not exist: $VAULT_PATH${NC}"
    exit 1
fi

# Check for .obsidian directory to verify it's an Obsidian vault
if [ ! -d "$VAULT_PATH/.obsidian" ]; then
    echo -e "${YELLOW}Warning: .obsidian directory not found. This may not be an Obsidian vault.${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}Ingesting Obsidian vault: $VAULT_PATH${NC}"
echo -e "Output name: ${GREEN}$OUTPUT_NAME${NC}"
echo ""

# Create temporary directory for processing
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Find all markdown files, excluding templates and hidden directories
echo "Finding markdown files..."
find "$VAULT_PATH" -type f -name "*.md" \
    ! -path "*/.obsidian/*" \
    ! -path "*/Templates/*" \
    ! -path "*/templates/*" \
    ! -path "*/Archive/*" \
    ! -path "*/archive/*" \
    > "$TEMP_DIR/file_list.txt"

FILE_COUNT=$(wc -l < "$TEMP_DIR/file_list.txt")
echo -e "Found ${GREEN}$FILE_COUNT${NC} markdown files"

if [ "$FILE_COUNT" -eq 0 ]; then
    echo -e "${RED}No markdown files found in vault${NC}"
    exit 1
fi

# Create output directory
OUTPUT_DIR="knowledge_base/obsidian"
mkdir -p "$OUTPUT_DIR"

# Process files
OUTPUT_FILE="$OUTPUT_DIR/${OUTPUT_NAME}.md"
echo -e "\nProcessing files into: ${GREEN}$OUTPUT_FILE${NC}\n"

cat > "$OUTPUT_FILE" << 'EOF'
# Obsidian Vault Export

This document contains the contents of an Obsidian vault for RAG indexing.

**Export Details:**
EOF

echo "- **Vault Path:** $VAULT_PATH" >> "$OUTPUT_FILE"
echo "- **Export Date:** $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUTPUT_FILE"
echo "- **File Count:** $FILE_COUNT" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Process each file
PROCESSED=0
while IFS= read -r file; do
    PROCESSED=$((PROCESSED + 1))
    REL_PATH="${file#$VAULT_PATH/}"

    echo -ne "\r[${PROCESSED}/${FILE_COUNT}] Processing: $REL_PATH"

    # Add file header
    echo "## File: $REL_PATH" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

    # Process the markdown file
    python3 - "$file" "$VAULT_PATH" >> "$OUTPUT_FILE" << 'PYTHON'
import sys
import re
import os

def process_obsidian_markdown(file_path, vault_path):
    """Process Obsidian markdown, converting wiki links and handling special syntax"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Convert wiki-style links [[Note Name]] to markdown links
    # Keep the link text for context
    content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'[\2](\1)', content)
    content = re.sub(r'\[\[([^\]]+)\]\]', r'[[\1]]', content)

    # Convert ![[image.png]] embeds to notes
    content = re.sub(r'!\[\[([^\]]+)\]\]', r'[Embedded: \1]', content)

    # Handle tags - keep them as-is for searchability
    # #tag format is already markdown-compatible

    # Handle dataview queries - convert to text
    content = re.sub(r'```dataview\n(.*?)```', r'[Dataview Query: \1]', content, flags=re.DOTALL)

    # Handle callouts/admonitions - keep the content, note the type
    content = re.sub(r'>\s*\[!(\w+)\]([+-]?)\s*([^\n]*)\n((?:>.*\n?)*)',
                     lambda m: f'> **{m.group(1).upper()}:** {m.group(3)}\n{m.group(4)}',
                     content)

    print(content)
    print("\n---\n")

if __name__ == '__main__':
    process_obsidian_markdown(sys.argv[1], sys.argv[2])
PYTHON

done < "$TEMP_DIR/file_list.txt"

echo -e "\n\n${GREEN}✓ Processing complete${NC}"
echo -e "Output file: ${GREEN}$OUTPUT_FILE${NC}"
echo -e "Size: $(du -h "$OUTPUT_FILE" | cut -f1)"

# Ask if user wants to restart RAG service
echo ""
read -p "Restart RAG service to index new content? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo -e "\n${YELLOW}Restarting RAG service...${NC}"
    docker-compose restart rag-api
    echo -e "${GREEN}✓ Service restarted${NC}"
    echo ""
    echo "Wait ~30 seconds for indexing to complete, then check:"
    echo "  curl http://localhost:8000/health"
else
    echo ""
    echo "To index manually, run:"
    echo "  docker-compose restart rag-api"
fi

echo ""
echo -e "${GREEN}✓ Done!${NC}"
echo ""
echo "Try querying your vault:"
echo "  curl -X POST http://localhost:8000/query \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\": \"your search query\", \"top_k\": 5}'"
