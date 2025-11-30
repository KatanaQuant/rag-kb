# MCP Server (stdio) - Legacy

> **DEPRECATED**: This stdio-based MCP server is legacy. Use HTTP transport instead.

## Recommended: HTTP Transport (v1.9.0+)

HTTP transport is simpler and doesn't require Node.js:

```bash
# Claude Code
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp

# Verify
claude mcp list
```

See setup guides:
- [MCP_CLAUDE.md](../docs/MCP_CLAUDE.md) - Claude Code
- [MCP_CODEX.md](../docs/MCP_CODEX.md) - OpenAI Codex
- [MCP_GEMINI.md](../docs/MCP_GEMINI.md) - Google Gemini
- [MCP_AMP.md](../docs/MCP_AMP.md) - Amp (Sourcegraph)

---

## Legacy: stdio Transport

If HTTP doesn't work, this Node.js bridge is still available.

### Requirements

- Node.js v14+
- RAG API running (`docker-compose up -d`)

### Setup

```bash
# Install dependencies
cd mcp-server
npm install

# Add to Claude Code
claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb-stdio \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

### Tools Available

| Tool | Description |
|------|-------------|
| `query_kb` | Semantic search across indexed docs |
| `list_indexed_documents` | See what's in your KB |
| `get_kb_stats` | Check KB status and stats |

### Environment Variables

- `RAG_API_URL` - URL of your RAG API (default: `http://localhost:8000`)

### Troubleshooting

1. **Check RAG API is running:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Check MCP server manually:**
   ```bash
   node index.js  # Should wait for stdio input
   ```

3. **Verify path in config:**
   - Use absolute paths
   - Ensure `node` is in your PATH

---

## Migration to HTTP

```bash
# Remove old stdio server
claude mcp remove rag-kb-stdio

# Add HTTP server
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp

# Verify
claude mcp list
```

**Why migrate?**
- No Node.js dependency
- Simpler setup (one command)
- Direct connection to Docker
- Remote access support (LAN/internet)
