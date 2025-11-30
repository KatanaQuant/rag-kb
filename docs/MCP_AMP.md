# MCP Integration (Amp)

Use your knowledge base with Amp (Sourcegraph's AI coding agent) via MCP (Model Context Protocol).

> **Other AI Assistants**: See [MCP_CLAUDE.md](MCP_CLAUDE.md) for Claude Code, [MCP_CODEX.md](MCP_CODEX.md) for OpenAI Codex, or [MCP_GEMINI.md](MCP_GEMINI.md) for Google Gemini.

---

## Prerequisites

1. RAG service running:
   ```bash
   docker-compose up -d
   curl http://localhost:8000/health
   ```

2. Amp VSCode extension installed (see [Installing Amp](#installing-amp-vscode-extension) below)

---

## Quick Setup (HTTP Transport - Recommended)

**HTTP transport is the simplest setup** - no Node.js required, direct connection to Docker.

### Which URL to Use?

| Scenario | URL | Example |
|----------|-----|---------|
| **Same machine** | `http://localhost:8000/mcp` | RAG and Amp on same computer |
| **Local network (LAN)** | `http://LAN_IP:8000/mcp` | Laptop → Desktop on same WiFi/network |
| **Remote/Internet** | `http://PUBLIC_IP:8000/mcp` | Access from anywhere (requires port forwarding) |

### Setup Command (Global)

```bash
# Same machine - use localhost
amp mcp add --transport http rag-kb http://localhost:8000/mcp

# Local network - use server's LAN IP
amp mcp add --transport http rag-kb http://192.168.1.100:8000/mcp

# Verify connection
amp mcp list
```

**After adding**: Reload VSCode: `Ctrl+Shift+P` → "Developer: Reload Window"

### Finding Your Server's IP

```bash
# On the RAG server machine:

# LAN IP (for local network access)
ip addr show | grep "inet " | grep -v 127.0.0.1
# Example output: 192.168.1.100

# Public IP (for internet access - requires router port forwarding)
curl -s ifconfig.me
```

---

## Migrating from stdio to HTTP (v1.9.0+)

If you previously used stdio transport, migrate to HTTP:

```bash
# Step 1: Remove old stdio server
amp mcp remove rag-kb

# Step 2: Add HTTP server
amp mcp add --transport http rag-kb http://localhost:8000/mcp

# Step 3: Verify
amp mcp list
```

**Why migrate?**
- No Node.js required - direct connection to Docker
- Simpler setup - one command, no path configuration
- Remote access - works with any server IP
- Future-proof - HTTP is the MCP standard going forward

---

## Legacy: stdio Transport (Deprecated)

> **Deprecation Notice**: stdio transport will be removed in v2.0. Please migrate to HTTP.

If HTTP doesn't work, use stdio transport (requires Node.js):

```bash
# Requires Node.js v14+
node --version

# Add MCP server with stdio
amp mcp add rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

---

## Installing Amp VSCode Extension

### Option 1: VSCode Marketplace (Recommended)

Install the [Amp extension](https://marketplace.visualstudio.com/items?itemName=sourcegraph.amp) from VSCode marketplace:

1. Open VSCode
2. Go to Extensions (`Ctrl+Shift+X`)
3. Search for "Amp" (by Sourcegraph)
4. Click Install

### Option 2: Manual Installation

Visit [ampcode.com](https://ampcode.com) and follow the installation instructions.

---

## Verify Installation

```bash
amp mcp list
# Should show: rag-kb - Connected
```

**In VSCode**: Open Amp panel → check MCP tools are available.

---

## Network Scenarios

### Scenario 1: Same Machine (localhost)

```
[Your Computer]
├── Amp / VSCode
└── Docker (rag-api on port 8000)

URL: http://localhost:8000/mcp
```

### Scenario 2: Local Network (LAN)

```
[Your Laptop]                    [Desktop Server]
├── Amp / VSCode           →     └── Docker (rag-api)
                                     IP: 192.168.1.100

URL: http://192.168.1.100:8000/mcp
```

### Scenario 3: Remote/Internet

```
[Your Laptop]                    [Remote Server]
├── Amp / VSCode           →     └── Docker (rag-api)
    (anywhere)                       Public IP: 203.0.113.50

URL: http://203.0.113.50:8000/mcp
```

**Security Warning**: Exposing to internet without authentication is risky. Consider VPN or SSH tunnel.

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

## Manual Config (settings.json)

If CLI doesn't work:

**HTTP Transport (recommended):**
```json
{
  "amp.mcpServers": {
    "rag-kb": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**For remote server:**
```json
{
  "amp.mcpServers": {
    "rag-kb": {
      "url": "http://192.168.1.100:8000/mcp"
    }
  }
}
```

**stdio Transport (legacy):**
```json
{
  "amp.mcpServers": {
    "rag-kb": {
      "command": "node",
      "args": ["/absolute/path/to/rag-kb/mcp-server/index.js"],
      "env": {
        "RAG_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

### Config File Locations

- **macOS/Linux**: `~/.config/amp/settings.json`
- **Windows**: `%APPDATA%\amp\settings.json`
- **Project-specific**: `.amp/settings.json`

---

## Troubleshooting

### MCP Not Connecting

```bash
# 1. Check RAG is running
curl http://localhost:8000/health

# 2. Check MCP endpoint
curl http://localhost:8000/mcp

# 3. Check MCP status
amp mcp list

# 4. If "Failed to connect" - remove and re-add
amp mcp remove rag-kb
amp mcp add --transport http rag-kb http://localhost:8000/mcp
```

### HTTP vs stdio Comparison

| Feature | HTTP (Recommended) | stdio (Legacy) |
|---------|-------------------|----------------|
| **Setup** | Simple (one command) | Requires Node.js |
| **Dependencies** | Docker only | Docker + Node.js |
| **Remote access** | Direct URL | SSH tunnel or local |
| **Use case** | All scenarios | Backwards compatibility |

### Settings Not Taking Effect

Reload VSCode after configuration changes:
- `Ctrl+Shift+P` → "Developer: Reload Window"

---

## See Also

- [MCP_CLAUDE.md](MCP_CLAUDE.md) - Claude Code setup
- [MCP_CODEX.md](MCP_CODEX.md) - OpenAI Codex setup
- [MCP_GEMINI.md](MCP_GEMINI.md) - Google Gemini setup
- [MCP_NETWORK.md](MCP_NETWORK.md) - Network configuration details
- [USAGE.md](USAGE.md) - Query methods

---

## References

- [Amp Owner's Manual](https://ampcode.com/manual)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

Sources:
- [Amp Streamable HTTP Transport](https://ampcode.com/news/streamable-mcp)
- [Amp MCP Setup Guide](https://github.com/sourcegraph/amp-examples-and-guides/blob/main/guides/amp-mcp-setup-guide.md)
