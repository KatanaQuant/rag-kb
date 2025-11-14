# Content Sources Reference

Quick reference for ingesting different types of content into the RAG knowledge base.

---

## Obsidian Vaults

### Basic Ingestion
```bash
./ingest-obsidian.sh ~/Documents/MyVault vault-name
```

### Advanced (Full Feature Support)
```bash
python api/obsidian_processor.py ~/Documents/MyVault knowledge_base/obsidian/vault.md
docker-compose restart rag-api
```

**Supported features:** Wiki links, callouts, frontmatter, tags, tasks, dataview queries, highlights

**Documentation:** [docs/OBSIDIAN_INTEGRATION.md](OBSIDIAN_INTEGRATION.md)

---

## Code Repositories

### Simple (Recommended)
```bash
./export-codebase-simple.sh /path/to/project > knowledge_base/code/project-name.md
```

### With Directory Tree
```bash
./export-codebase.sh /path/to/project > knowledge_base/code/project-name-full.md
```

### For Analysis
```bash
./export-for-analysis.sh /path/to/project "Description" > knowledge_base/code/project-analysis.md
```

**Tip:** Add your own notes/analysis to the exported markdown before indexing.

---

## Books & Documents

### PDFs
```bash
cp ~/Downloads/book.pdf knowledge_base/books/
docker-compose restart rag-api
```

### Text Files
```bash
cp ~/Downloads/article.txt knowledge_base/articles/
docker-compose restart rag-api
```

### Word Documents (.docx)
```bash
cp ~/Documents/paper.docx knowledge_base/papers/
docker-compose restart rag-api
```

---

## Web Content

### Articles (Using Pandoc)
```bash
curl https://example.com/article | pandoc -f html -t markdown \
  > knowledge_base/articles/article-name.md
docker-compose restart rag-api
```

### Documentation Sites
```bash
# Use tools like wget or httrack to download
wget -r -A.html --convert-links -P docs_dump https://docs.example.com

# Convert to single markdown
find docs_dump -name "*.html" -exec pandoc {} -f html -t markdown -o knowledge_base/docs/site-docs.md +
```

### GitHub README Files
```bash
# Download README
curl https://raw.githubusercontent.com/user/repo/main/README.md \
  > knowledge_base/github/repo-readme.md
docker-compose restart rag-api
```

---

## Research Papers

### From arXiv
```bash
# Download PDF
curl https://arxiv.org/pdf/2103.xxxxx.pdf -o knowledge_base/papers/paper-name.pdf
docker-compose restart rag-api
```

### From Local Collection
```bash
# Batch copy all PDFs
cp ~/Papers/ML/*.pdf knowledge_base/papers/ml/
docker-compose restart rag-api
```

---

## Notion Exports

### Export from Notion
1. In Notion: Settings → Export → Markdown & CSV
2. Extract the zip file
3. Process the markdown files:

```bash
# Simple approach - copy all markdown
find ~/Downloads/notion-export -name "*.md" -exec cp {} knowledge_base/notion/ \;
docker-compose restart rag-api

# Advanced - use Python to process (preserves structure)
python api/obsidian_processor.py ~/Downloads/notion-export knowledge_base/notion/notion-export.md
docker-compose restart rag-api
```

**Note:** Notion uses similar syntax to Obsidian, so the Obsidian processor works reasonably well.

---

## Jupyter Notebooks

### Convert to Markdown
```bash
jupyter nbconvert --to markdown notebook.ipynb
cp notebook.md knowledge_base/notebooks/
docker-compose restart rag-api
```

### Batch Convert
```bash
find ~/Projects -name "*.ipynb" -exec jupyter nbconvert --to markdown {} \;
find ~/Projects -name "*.md" -exec cp {} knowledge_base/notebooks/ \;
docker-compose restart rag-api
```

---

## Slack/Discord Exports

### Slack Export
1. Export from Slack (JSON format)
2. Convert to markdown:

```python
import json
from pathlib import Path

export_dir = Path("slack-export")
output = []

for channel_file in export_dir.glob("*/*.json"):
    with open(channel_file) as f:
        messages = json.load(f)

    for msg in messages:
        if 'text' in msg:
            output.append(f"**{msg.get('user', 'Unknown')}:** {msg['text']}")

Path("knowledge_base/slack/export.md").write_text("\n\n".join(output))
```

```bash
docker-compose restart rag-api
```

---

## Email Archives

### From Thunderbird/Mail.app
```bash
# Export as .txt or .eml, convert to markdown
# Use tools like mu or notmuch to extract

mu find date:6m..now --format=plain > knowledge_base/email/recent-emails.txt
docker-compose restart rag-api
```

---

## Personal Notes Apps

### Apple Notes
Use applescript or third-party tools to export, then:
```bash
cp ~/exports/apple-notes/*.txt knowledge_base/notes/
docker-compose restart rag-api
```

### Evernote
1. Export as .enex (XML format)
2. Use `enex2md` tool:
```bash
pip install enex2md
enex2md export.enex knowledge_base/evernote/
docker-compose restart rag-api
```

### Google Keep
Use Google Takeout to export, then process JSON:
```bash
# Process Keep JSON to markdown
python -c "
import json
from pathlib import Path

keep_json = json.load(open('Takeout/Keep/Keep.json'))
output = []

for note in keep_json:
    title = note.get('title', 'Untitled')
    text = note.get('textContent', '')
    output.append(f'# {title}\n\n{text}\n\n---\n')

Path('knowledge_base/keep/notes.md').write_text(''.join(output))
"
docker-compose restart rag-api
```

---

## Podcast Transcripts

### From YouTube (with yt-dlp)
```bash
yt-dlp --write-auto-sub --skip-download URL
# Convert .vtt to text
sed 's/<[^>]*>//g' subtitle.en.vtt | sed '/^$/d' > knowledge_base/transcripts/podcast.txt
docker-compose restart rag-api
```

### From Podcast Apps
Many apps allow transcript export. Save as .txt and copy to `knowledge_base/transcripts/`.

---

## API Documentation

### OpenAPI/Swagger
```bash
# Download OpenAPI spec
curl https://api.example.com/openapi.json | jq -r '.paths | to_entries[] | "\(.key)\n\(.value | tostring)\n"' \
  > knowledge_base/api/api-docs.txt
docker-compose restart rag-api
```

---

## Database Schemas

### From PostgreSQL
```bash
pg_dump --schema-only mydb | grep -E "(CREATE|COMMENT)" \
  > knowledge_base/schemas/db-schema.sql
docker-compose restart rag-api
```

### From MySQL
```bash
mysqldump --no-data mydb > knowledge_base/schemas/db-schema.sql
docker-compose restart rag-api
```

---

## Tips

1. **Organize by type:** Use subdirectories like `books/`, `code/`, `articles/`
2. **Descriptive names:** Use clear filenames for better source attribution
3. **Consolidate when possible:** Combine related files into one markdown for efficiency
4. **Test queries:** After indexing, run a test query to verify content is searchable
5. **Re-index periodically:** Content updates won't reflect until service restart

---

## Cleanup Examples

Once you've verified ingestion works, remove example files:

```bash
# Remove example books (keep your own)
rm knowledge_base/*.txt

# Keep only codebases you actually reference
# The systematic_trading folder is an example - remove if not needed
```

Then restart:
```bash
docker-compose restart rag-api
```

---

## See Also

- [Obsidian Integration Guide](OBSIDIAN_INTEGRATION.md) - Full Obsidian features
- [Workflow Guide](WORKFLOW.md) - Code analysis workflows
- [Main README](../README.md) - Setup and usage
