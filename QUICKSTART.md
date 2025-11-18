# Quick Reference Card

One-page cheat sheet for common RAG operations.

**Current Version**: v0.8.0-alpha

---

## First Time Setup

```bash
# 1. Clone
git clone https://github.com/yourusername/rag-kb.git
cd rag-kb

# 2. Add content (PDF, Markdown, Code)
cp ~/Documents/*.pdf knowledge_base/books/
cp -r ~/projects/myapp knowledge_base/code/

# 3. Start
docker-compose up --build -d

# 4. Configure Claude Code (one-time)
# Edit ~/.config/claude-code/mcp.json:
{
  "mcpServers": {
    "rag-kb": {
      "command": "node",
      "args": ["/full/path/to/rag-kb/mcp-server/index.js"],
      "env": {"RAG_API_URL": "http://localhost:8000"}
    }
  }
}

# 5. In VSCode: Ctrl+Shift+P → "MCP: List Servers"
```

---

## Daily Commands

```bash
# Start service
docker-compose up -d

# Stop service
docker-compose down

# Check status
curl http://localhost:8000/health

# View logs
docker-compose logs -f rag-api

# Quick search
curl -X POST http://localhost:8000/query -d '{"text": "query", "top_k": 3}'
```

---

## Adding Content

```bash
# Documents (PDF, DOCX, EPUB, Markdown)
cp ~/Downloads/book.pdf knowledge_base/books/
cp ~/Documents/*.md knowledge_base/notes/
docker-compose restart rag-api

# Code repositories (Python, Java, TypeScript, JavaScript, C#)
# Just copy the entire directory - auto-filters build artifacts
cp -r ~/projects/myapp knowledge_base/code/
docker-compose restart rag-api

# Watch for automatic indexing
docker-compose logs -f rag-api
```

---

## Migration to New Machine

```bash
# Old machine:
tar -czf rag-migration.tar.gz data/ knowledge_base/ docker-compose.yml
scp rag-migration.tar.gz user@new-machine:~/

# New machine:
tar -xzf rag-migration.tar.gz
docker-compose up --build -d
# All indexed content ready immediately!
```

---

## Claude Code Usage

**Each VSCode session:**
1. `Ctrl+Shift+P` → "MCP: List Servers"
2. Ask Claude naturally: "What's in my knowledge base about [topic]?"

---

## Troubleshooting

```bash
# Port conflict
echo "RAG_PORT=8001" > .env
docker-compose up -d

# No results
curl -X POST http://localhost:8000/index -d '{"force_reindex": true}'

# Check what's indexed
curl http://localhost:8000/documents | jq

# View errors
docker-compose logs rag-api | grep -i error
```

---

## Common Queries

```bash
# In Claude Code, just ask:
"What does my codebase say about authentication?"
"Find all my notes about React hooks"
"How does [book name] explain [concept]?"
"Show me the implementation of the login function"

# Via curl:
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your question here", "top_k": 5}'
```

---

## Supported File Types

**Documents**: `.pdf`, `.docx`, `.epub`, `.md`, `.markdown`, `.txt`

**Code**: `.py`, `.java`, `.ts`, `.tsx`, `.js`, `.jsx`, `.cs`

**Auto-excluded**: `node_modules/`, `__pycache__/`, `.git/`, `venv/`, build artifacts, minified files

---

## Backup

```bash
# Quick backup
tar -czf ~/backups/rag-$(date +%Y%m%d).tar.gz data/ knowledge_base/

# Database only
cp data/knowledge_base.db ~/backups/kb-$(date +%Y%m%d).db
```

---

## Full Documentation

- **[README.md](README.md)** - Complete setup guide
- **[docs/OBSIDIAN_INTEGRATION.md](docs/OBSIDIAN_INTEGRATION.md)** - Obsidian vault sync
- **[docs/CONTENT_SOURCES.md](docs/CONTENT_SOURCES.md)** - All content types
- **[.agent/workflows.md](.agent/workflows.md)** - Standard procedures
