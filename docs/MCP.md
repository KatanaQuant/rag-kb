# MCP Integration

Connect AI coding assistants to your RAG knowledge base via MCP (Model Context Protocol).

---

## Quick Setup

### 1. Start RAG Service

```bash
docker-compose up -d
curl http://localhost:8000/health
```

### 2. Add MCP Server

Choose your AI assistant:

**Claude Code:**
```bash
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp
```

**OpenAI Codex:**
```bash
codex --enable rmcp_client
codex mcp add --transport http rag-kb http://localhost:8000/mcp
```

**Google Gemini:**
```bash
npm install -g @google/gemini-cli
gemini mcp add --transport http rag-kb http://localhost:8000/mcp
```

**Amp (Sourcegraph):**
```bash
amp mcp add --transport http rag-kb http://localhost:8000/mcp
```

### 3. Verify

```bash
# Check connection (use your CLI)
claude mcp list
# or: codex mcp list / gemini mcp list / amp mcp list
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `query_kb` | Semantic search across documents |
| `list_indexed_documents` | List indexed files |
| `get_kb_stats` | Knowledge base statistics |

### Query Parameters

```
query: "your search query"
top_k: 5          # Number of results (default: 5)
threshold: 0.3    # Minimum similarity score (0-1)
```

---

## Network Scenarios

### Same Machine

```bash
# URL: http://localhost:8000/mcp
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp
```

### Local Network (LAN)

```bash
# Find server IP
ip addr show | grep "inet " | grep -v 127.0.0.1
# Example: 192.168.1.100

# URL: http://192.168.1.100:8000/mcp
claude mcp add --transport http --scope user rag-kb http://192.168.1.100:8000/mcp
```

### Remote Access

```bash
# URL: http://PUBLIC_IP:8000/mcp
# Requires: Router port forwarding, firewall open

# Security recommendation: Use SSH tunnel
ssh -L 8000:localhost:8000 user@server
# Then use localhost:8000
```

---

## Manual Configuration

If CLI doesn't work, edit config files directly.

### Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "rag-kb": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### OpenAI Codex (`~/.codex/config.toml`)

```toml
[features]
rmcp_client = true

[mcp_servers.rag-kb]
url = "http://localhost:8000/mcp"
```

### Google Gemini (`~/.gemini/settings.json`)

```json
{
  "mcpServers": {
    "rag-kb": {
      "httpUrl": "http://localhost:8000/mcp"
    }
  }
}
```

### Amp (`~/.config/amp/settings.json`)

```json
{
  "amp.mcpServers": {
    "rag-kb": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

---

## Troubleshooting

### Connection Failed

```bash
# 1. Check RAG is running
curl http://localhost:8000/health

# 2. Check MCP endpoint
curl http://localhost:8000/mcp

# 3. Remove and re-add
claude mcp remove rag-kb
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp
```

### Remote Connection Refused

```bash
# Check firewall
sudo ufw allow 8000/tcp

# Check Docker binding
docker ps  # Should show 0.0.0.0:8000->8000
```

### VSCode Not Seeing MCP

Reload window: `Ctrl+Shift+P` → "Developer: Reload Window"

---

## Prioritizing Your Knowledge Base

Create `.claude/claude.md` in your project:

```markdown
## Knowledge Base Priority

Use `mcp__rag-kb__query_kb` BEFORE general knowledge for technical questions.

When answering:
1. Query RAG first
2. Cite sources from knowledge base
3. Use general knowledge only if RAG score < 0.3
```

---

## See Also

- [USAGE.md](USAGE.md) - Query methods
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
