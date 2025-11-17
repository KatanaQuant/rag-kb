# Obsidian Integration Guide

Complete guide for ingesting Obsidian vaults into the RAG knowledge base.

## Quick Start

### Simple Ingestion (Shell Script)

```bash
# Ingest entire vault
./ingest-obsidian.sh ~/Documents/MyVault

# Ingest with custom name
./ingest-obsidian.sh ~/Documents/MyVault my-notes
```

The script will:
1. Find all markdown files (excluding templates/archives)
2. Process Obsidian-specific syntax
3. Export to `knowledge_base/obsidian/<name>.md`
4. Offer to restart RAG service for indexing

### Advanced Processing (Python)

```bash
# Requires pyyaml
pip install pyyaml

# Process vault with full Obsidian feature support
python api/obsidian_processor.py ~/Documents/MyVault knowledge_base/obsidian/vault.md

# Restart RAG to index
docker-compose restart rag-api
```

## Features

### Supported Obsidian Syntax

#### Wiki Links
```markdown
# Obsidian                    # After Processing
[[Note Name]]            →    [[Note Name]]
[[Note|Display Text]]    →    [Display Text](→ Note)
[[Note#Section]]         →    [Note](→ Note / Section)
```

#### Embeds
```markdown
# Obsidian                    # After Processing
![[image.png]]           →    [Embedded file: image.png]
![[Other Note]]          →    [Embedded note: Other Note]
```

#### Callouts/Admonitions
```markdown
# Obsidian
> [!note] Important
> This is a note callout

# After Processing
**NOTE: Important**
This is a note callout
```

Supported callout types: `note`, `tip`, `warning`, `danger`, `question`, `info`, `success`, etc.

#### Frontmatter (YAML)
```markdown
---
title: My Note
tags: [project, important]
date: 2025-11-13
---

# After Processing
**Metadata:**
- title: My Note
- tags: [project, important]
- date: 2025-11-13
```

#### Tags
```markdown
#tag #nested/tag          # Preserved as-is (already markdown-compatible)
```

#### Tasks
```markdown
- [ ] Todo                # Standard markdown
- [x] Done                # Standard markdown
- [>] Forwarded          # Obsidian-specific (preserved)
- [?] Question           # Obsidian-specific (preserved)
```

#### Highlights
```markdown
==highlighted text==  →  **highlighted text**
```

#### Dataview Queries
```markdown
# Obsidian
```dataview
TABLE file.ctime FROM #project
```

# After Processing
[Dataview Query]
```
TABLE file.ctime FROM #project
```
```

#### Comments
```markdown
%%This is a comment%%  →  [removed]
```

## Configuration

### Excluding Directories

Edit `ingest-obsidian.sh` to skip additional directories:

```bash
find "$VAULT_PATH" -type f -name "*.md" \
    ! -path "*/.obsidian/*" \
    ! -path "*/Templates/*" \
    ! -path "*/Private/*" \      # Add your exclusions
    ! -path "*/Drafts/*" \       # Add your exclusions
    > "$TEMP_DIR/file_list.txt"
```

Or use Python processor:

```python
processor = ObsidianProcessor(vault_path)
processor.export_to_markdown(
    output_path,
    exclude_patterns=['Templates', 'Archive', 'Private', 'Drafts']
)
```

### Auto-sync on Changes

Use a file watcher to auto-sync when vault changes:

```bash
#!/bin/bash
# watch-vault.sh

VAULT_PATH="$1"
OUTPUT_NAME="${2:-obsidian-vault}"

# Install: apt-get install inotify-tools
inotifywait -m -r -e modify,create,delete "$VAULT_PATH" --include '.*\.md$' |
while read -r directory event filename; do
    echo "Change detected: $event $filename"
    ./ingest-obsidian.sh "$VAULT_PATH" "$OUTPUT_NAME"
done
```

## Usage Patterns

### Pattern 1: Personal Knowledge Base

```bash
# Ingest your entire personal notes
./ingest-obsidian.sh ~/Obsidian/PersonalVault personal-kb

# Query your notes via RAG
curl -X POST http://localhost:8000/query \
  -d '{"text": "what did I learn about python decorators?", "top_k": 5}'
```

### Pattern 2: Project Documentation

```bash
# Ingest project-specific vault
./ingest-obsidian.sh ~/Projects/MyApp/docs project-docs

# Ask questions about your project
curl -X POST http://localhost:8000/query \
  -d '{"text": "how does authentication work?", "top_k": 3}'
```

### Pattern 3: Multiple Vaults

```bash
# Ingest multiple vaults with different names
./ingest-obsidian.sh ~/Obsidian/Work work-notes
./ingest-obsidian.sh ~/Obsidian/Personal personal-notes
./ingest-obsidian.sh ~/Obsidian/Learning learning-notes

# Restart once after all ingestions
docker-compose restart rag-api

# Query across all vaults
curl -X POST http://localhost:8000/query \
  -d '{"text": "kubernetes deployment strategies", "top_k": 5}'
```

### Pattern 4: Incremental Updates

```bash
# Re-run ingestion to update (overwrites previous export)
./ingest-obsidian.sh ~/Obsidian/Vault vault-latest

# RAG automatically detects file changes and reindexes
docker-compose restart rag-api
```

## Workflow Integration

### Claude Code / MCP

Once ingested, your Obsidian notes are available through MCP:

```
# In Claude Code:
"What does my note on Docker say about networking?"
"Find all references to React hooks in my notes"
"Summarize my project retrospectives"
```

### Command Line

```bash
# Add to your shell aliases
alias kb-search='f(){ curl -s -X POST http://localhost:8000/query -H "Content-Type: application/json" -d "{\"text\": \"$1\", \"top_k\": 5}" | jq -r ".results[] | \"\(.source)\n\(.content)\n---\""; }; f'

# Usage
kb-search "python async patterns"
```

### Alfred/Raycast

Create a workflow/script command:

```bash
#!/bin/bash
# Search Obsidian notes via RAG

QUERY="$1"
RESULT=$(curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$QUERY\", \"top_k\": 3}")

echo "$RESULT" | jq -r '.results[] | "\(.source)\n\(.content)\n"'
```

## Troubleshooting

### Links Not Resolving

**Problem:** Wiki links show as `[[Note Name]]` instead of resolving.

**Solution:** Use Python processor which builds a file map:

```bash
python api/obsidian_processor.py ~/vault knowledge_base/obsidian/vault.md
```

### Large Vault Takes Too Long

**Problem:** 1000+ notes take several minutes to process.

**Solution:** Process in batches or exclude large directories:

```bash
# Process only specific subdirectory
./ingest-obsidian.sh ~/Vault/Projects projects-only

# Or exclude large folders
# Edit ingest-obsidian.sh to add exclusions
```

### Dataview Queries Breaking

**Problem:** Complex dataview queries cause parsing errors.

**Solution:** The processor wraps them as code blocks. If issues persist, exclude dataview entirely:

```python
# In obsidian_processor.py, comment out:
# content = self.process_dataview(content)
```

### Special Characters in Note Names

**Problem:** Notes with special characters don't index properly.

**Solution:** Use Python processor which handles encoding:

```bash
python api/obsidian_processor.py ~/vault output.md
```

## Performance

### Ingestion Speed

- **Shell script:** ~50 files/sec (simple processing)
- **Python processor:** ~20 files/sec (full feature support)

### Vault Size Guidelines

| Notes | Processing Time | Output Size | Query Speed |
|-------|----------------|-------------|-------------|
| <100  | <5s            | <1MB        | <50ms       |
| 100-500 | <30s         | 1-5MB       | <100ms      |
| 500-1000 | ~1min        | 5-10MB      | <200ms      |
| 1000+ | ~2min          | 10MB+       | <500ms      |

## Advanced Usage

### Custom Processing

Extend `ObsidianProcessor` for custom syntax:

```python
from api.obsidian_processor import ObsidianProcessor

class CustomProcessor(ObsidianProcessor):
    def process_custom_syntax(self, content: str) -> str:
        # Your custom processing
        return content

    def process_file(self, file_path: Path) -> Dict:
        result = super().process_file(file_path)
        result['content'] = self.process_custom_syntax(result['content'])
        return result
```

### Filtering by Tags

```python
processor = ObsidianProcessor(vault_path)
notes = processor.process_vault()

# Filter by tag
project_notes = [
    n for n in notes
    if n['frontmatter'] and 'project' in n['frontmatter'].get('tags', [])
]

# Export filtered notes only
with open('project_notes.md', 'w') as f:
    for note in project_notes:
        f.write(f"## {note['name']}\n{note['content']}\n---\n")
```

### Periodic Sync

Add to crontab for daily sync:

```bash
# Sync vault every night at 2 AM
0 2 * * * /path/to/RAG/ingest-obsidian.sh ~/Obsidian/Vault vault-backup && docker-compose -f /path/to/RAG/docker-compose.yml restart rag-api
```

## Best Practices

1. **Use descriptive output names** for multiple vaults
2. **Exclude private/sensitive notes** from ingestion
3. **Re-ingest periodically** to keep RAG up-to-date
4. **Test queries** after ingestion to verify indexing
5. **Keep vault structure clean** (use subdirectories, consistent naming)

## FAQ

**Q: Will this modify my Obsidian vault?**
A: No, ingestion is read-only. It copies and processes files.

**Q: Do I need to keep RAG updated when I edit notes?**
A: Yes, re-run ingestion after significant changes.

**Q: Can I ingest multiple vaults?**
A: Yes! Run the script multiple times with different names.

**Q: What about binary attachments (PDFs, images)?**
A: Attachments are noted as `[Embedded: filename]` but not indexed. Add them separately to `knowledge_base/` if needed.

**Q: Does this work with Obsidian Sync?**
A: Yes, ingest the synced local vault folder.

**Q: Can I use this with Logseq?**
A: Partially - Logseq uses similar markdown but different linking. May need custom processor.

## See Also

- [Main README](../README.md) - RAG setup
- [Workflow Guide](WORKFLOW.md) - Code analysis workflows
- [Migration Guide](MIGRATION_GUIDE.md) - Moving from file-based context
