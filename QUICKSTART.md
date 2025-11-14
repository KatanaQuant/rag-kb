# Quick Reference Card

One-page cheat sheet for common RAG operations.

---

## First Time Setup

```bash
# 1. Clone
git clone https://github.com/yourusername/rag-kb.git
cd rag-kb

# 2. Add content
cp ~/Documents/*.pdf knowledge_base/books/

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
# Books/PDFs
cp ~/Downloads/book.pdf knowledge_base/books/
docker-compose restart rag-api

# Obsidian vault
./ingest-obsidian.sh ~/Documents/MyVault vault-name

# Code repository
./export-codebase-simple.sh ~/projects/myapp > knowledge_base/code/myapp.md
docker-compose restart rag-api
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
# ✅ All indexed content ready immediately!
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

# Via curl:
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your question here", "top_k": 5}'
```

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
