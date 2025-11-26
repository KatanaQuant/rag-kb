# MCP Integration (Claude Code)

Use your knowledge base with Claude Code via MCP (Model Context Protocol).

---

## Quick Setup

### 1. Start RAG service

```bash
docker-compose up -d
curl http://localhost:8000/health
```

### 2. Add MCP server

```bash
claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

### 3. Enable for projects

Edit `~/.claude.json`:
```json
{
  "projects": {
    "/path/to/your/project": {
      "enabledMcpjsonServers": ["rag-kb"]
    }
  }
}
```

### 4. Verify

```bash
claude mcp list
# Should show: rag-kb - Connected
```

Reload VSCode: `Ctrl+Shift+P` → "Developer: Reload Window"

---

## Making Claude Prioritize Your KB

By default, Claude may answer from training data. To prioritize your knowledge base:

### Option 1: Project Instructions (Recommended)

Create `.claude/claude.md` in your project:

```markdown
## Knowledge Base Priority

**CHECK THIS FIRST** for technical questions, APIs, or domain knowledge.
Use `mcp__rag-kb__query_knowledge_base` BEFORE general knowledge.

When answering:
1. Query RAG first with specific, detailed queries
2. Cite sources from the knowledge base
3. Only use general knowledge if RAG score < 0.3
```

### Option 2: Explicit Prompts

```
"Check my KB for information about [topic]"
"What do my docs say about [topic]?"
```

---

## MCP Tools Available

| Tool | Description |
|------|-------------|
| `query_knowledge_base` | Semantic search across indexed docs |
| `list_indexed_documents` | See what's in your KB |
| `get_kb_stats` | Check KB status and stats |

### Query Parameters

```
query: "your search query"
top_k: 5          # Number of results (default: 5)
threshold: 0.3    # Minimum similarity score (0-1)
```

### Threshold Guide

| Value | Use Case |
|-------|----------|
| 0.0 | Exploratory - returns everything |
| 0.3 | Balanced - good recall/precision |
| 0.5 | High confidence only |
| 0.7 | Very strict matching |

---

## Troubleshooting

### MCP Not Connecting

```bash
# 1. Check RAG is running
curl http://localhost:8000/health

# 2. Check MCP status
claude mcp list

# 3. If "Failed to connect" - re-add with correct path
claude mcp remove rag-kb
claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

### Node.js Version Error

```bash
node --version  # Should be v14+

# Upgrade to v20 LTS (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Claude Not Using KB

Add explicit project instructions (Option 1 above) or use explicit prompts.

### Too Many/Few Results

- Too many irrelevant: Increase `threshold` to 0.4-0.5
- Missing content: Lower `threshold` to 0.2, try different queries

---

## See Also

- [USAGE.md](USAGE.md) - Query methods
- [CONFIGURATION.md](CONFIGURATION.md) - Settings
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - More help
