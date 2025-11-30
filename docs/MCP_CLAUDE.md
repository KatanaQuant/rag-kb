# MCP Integration (Claude Code)

Use your knowledge base with Claude Code via MCP (Model Context Protocol).

> **Other AI Assistants**: See [MCP_CODEX.md](MCP_CODEX.md) for OpenAI Codex or [MCP_GEMINI.md](MCP_GEMINI.md) for Google Gemini.

---

## Prerequisites

1. RAG service running:
   ```bash
   docker-compose up -d
   curl http://localhost:8000/health
   ```

2. Claude CLI installed (see [Installing Claude CLI](#installing-claude-cli) below)

---

## Quick Setup (HTTP Transport - Recommended)

**HTTP transport is the simplest setup** - no Node.js required, direct connection to Docker.

### Which URL to Use?

| Scenario | URL | Example |
|----------|-----|---------|
| **Same machine** | `http://localhost:8000/mcp` | RAG and Claude on same computer |
| **Local network (LAN)** | `http://LAN_IP:8000/mcp` | Laptop → Desktop on same WiFi/network |
| **Remote/Internet** | `http://PUBLIC_IP:8000/mcp` | Access from anywhere (requires port forwarding) |

### Setup Command (Global - All Projects)

```bash
# Same machine - use localhost
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp

# Local network - use server's LAN IP (e.g., 192.168.1.100)
claude mcp add --transport http --scope user rag-kb http://192.168.1.100:8000/mcp

# Verify connection
claude mcp list
# Should show: rag-kb: http://...:8000/mcp (HTTP) - ✓ Connected
```

**For VSCode users**: Reload window after adding: `Ctrl+Shift+P` → "Developer: Reload Window"

### Finding Your Server's IP

```bash
# On the RAG server machine:

# LAN IP (for local network access)
ip addr show | grep "inet " | grep -v 127.0.0.1
# Example output: 192.168.1.100

# Public IP (for internet access - requires router port forwarding)
curl -s ifconfig.me
# Example output: 203.0.113.50
```

---

## Migrating from stdio to HTTP (v1.9.0+)

If you previously used stdio transport, migrate to HTTP:

```bash
# Step 1: Remove old stdio server
claude mcp remove rag-kb
# or if named differently:
claude mcp remove rag-kb-stdio

# Step 2: Add HTTP server (global)
claude mcp add --transport http --scope user rag-kb http://localhost:8000/mcp

# Step 3: Verify
claude mcp list
```

**Why migrate?**
- No Node.js required - direct connection to Docker
- Simpler setup - one command, no path configuration
- Remote access - works with any server IP
- Future-proof - HTTP is the MCP standard going forward

---

## Legacy: stdio Transport (Deprecated)

> **Deprecation Notice**: stdio transport will be removed in v2.0. Please migrate to HTTP.

If HTTP doesn't work (rare), use stdio transport (requires Node.js):

```bash
# Requires Node.js v14+
node --version

# Add MCP server with stdio (global)
claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb-stdio \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

---

## Installing Claude CLI

Choose based on your setup:

### Option 1: VSCode Extension (Recommended)

Install the [Claude Code extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) from VSCode marketplace. The `claude` command is available in VSCode's integrated terminal.

### Option 2: Native Installer

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
claude auth login
```

### Option 3: Use VSCode Binary Directly

```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
```

---

## Verify Installation

```bash
claude mcp list
# Should show: rag-kb - ✓ Connected
```

**In Claude Code chat**: Type `/mcp` to see connected servers and available tools.

---

## Network Scenarios

### Scenario 1: Same Machine (localhost)

```
[Your Computer]
├── Claude Code / VSCode
└── Docker (rag-api on port 8000)

URL: http://localhost:8000/mcp
```

### Scenario 2: Local Network (LAN)

```
[Your Laptop]                    [Desktop Server]
├── Claude Code / VSCode   →     └── Docker (rag-api)
                                     IP: 192.168.1.100

URL: http://192.168.1.100:8000/mcp
```

**Requirements**: Both devices on same network, firewall allows port 8000

### Scenario 3: Remote/Internet

```
[Your Laptop]                    [Remote Server]
├── Claude Code / VSCode   →     └── Docker (rag-api)
    (anywhere)                       Public IP: 203.0.113.50

URL: http://203.0.113.50:8000/mcp
```

**Requirements**: Router port forwarding (8000→server), firewall open

**Security Warning**: Exposing to internet without authentication is risky. Consider:
- VPN for secure access
- SSH tunnel: `ssh -L 8000:localhost:8000 user@server` then use `localhost:8000`

---

## Usage

### In VSCode (Extension)

Claude automatically has access to MCP tools. Ask questions naturally:
- "What does my knowledge base say about [topic]?"
- "Search my docs for [keyword]"

### In Terminal (CLI)

```bash
claude "What does my knowledge base say about refactoring?"
```

---

## Making the Assistant Prioritize Your KB

Create `.claude/claude.md` in your project:

```markdown
## Knowledge Base Priority

**CHECK THIS FIRST** for technical questions, APIs, or domain knowledge.
Use `mcp__rag-kb__query_kb` BEFORE general knowledge.

When answering:
1. Query RAG first with specific queries
2. Cite sources from the knowledge base
3. Only use general knowledge if RAG score < 0.3
```

---

## MCP Tools Available

| Tool | Description |
|------|-------------|
| `query_kb` | Semantic search across indexed docs |
| `list_indexed_documents` | See what's in your KB |
| `get_kb_stats` | Check KB status and stats |

### Query Parameters

```
query: "your search query"
top_k: 5          # Number of results (default: 5)
threshold: 0.3    # Minimum similarity score (0-1)
```

---

## Troubleshooting

### MCP Not Connecting

```bash
# 1. Check RAG is running (on server)
curl http://localhost:8000/health

# 2. Check MCP endpoint (on server)
curl http://localhost:8000/mcp

# 3. Check from client (if remote)
curl http://SERVER_IP:8000/health

# 4. Check MCP status
claude mcp list

# 5. If "Failed to connect" - remove and re-add
claude mcp remove rag-kb
claude mcp add --transport http --scope user rag-kb http://SERVER_IP:8000/mcp
```

### Connection Refused from Remote

1. **Check firewall** on server: `sudo ufw allow 8000/tcp`
2. **Check Docker binding**: Ensure `docker-compose.yml` has `ports: ["8000:8000"]`
3. **Test locally first**: `curl http://localhost:8000/health` on server

### HTTP vs stdio Comparison

| Feature | HTTP (Recommended) | stdio (Legacy) |
|---------|-------------------|----------------|
| **Setup** | Simple (one command) | Requires Node.js |
| **Dependencies** | Docker only | Docker + Node.js |
| **Remote access** | Direct URL | SSH tunnel or local |
| **Performance** | ~5-10ms latency | ~1ms latency |
| **Use case** | All scenarios | Backwards compatibility |

---

## Manual Config (~/.claude.json)

If CLI doesn't work:

**HTTP Transport (recommended):**
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

**For remote server:**
```json
{
  "mcpServers": {
    "rag-kb": {
      "type": "http",
      "url": "http://192.168.1.100:8000/mcp"
    }
  }
}
```

---

## See Also

- [MCP_NETWORK.md](MCP_NETWORK.md) - Network configuration details
- [MCP_CODEX.md](MCP_CODEX.md) - OpenAI Codex setup
- [MCP_GEMINI.md](MCP_GEMINI.md) - Google Gemini setup
- [USAGE.md](USAGE.md) - Query methods

---

## References

- [Claude Code Documentation](https://docs.anthropic.com/claude-code)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

Sources:
- [Claude Code MCP Docs](https://docs.claude.com/en/docs/claude-code/mcp)
- [Claude Code Remote MCP Support](https://www.infoq.com/news/2025/06/anthropic-claude-remote-mcp/)
