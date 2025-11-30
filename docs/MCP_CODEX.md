# MCP Integration (OpenAI Codex)

Use your knowledge base with OpenAI Codex (CLI and VSCode extension) via MCP.

> **Other AI Assistants**: See [MCP_CLAUDE.md](MCP_CLAUDE.md) for Claude Code or [MCP_GEMINI.md](MCP_GEMINI.md) for Google Gemini.

---

## Prerequisites

1. RAG service running:
   ```bash
   docker-compose up -d
   curl http://localhost:8000/health
   ```

2. Codex CLI installed (see [Installing Codex CLI](#installing-codex-cli) below)

---

## Quick Setup (HTTP Transport - Recommended)

**HTTP transport is the simplest setup** - no Node.js required, direct connection to Docker.

### Which URL to Use?

| Scenario | URL | Example |
|----------|-----|---------|
| **Same machine** | `http://localhost:8000/mcp` | RAG and Codex on same computer |
| **Local network (LAN)** | `http://LAN_IP:8000/mcp` | Laptop → Desktop on same WiFi/network |
| **Remote/Internet** | `http://PUBLIC_IP:8000/mcp` | Access from anywhere (requires port forwarding) |

### Setup Command (Global)

```bash
# Enable HTTP transport (required once)
codex --enable rmcp_client

# Same machine - use localhost
codex mcp add --transport http rag-kb http://localhost:8000/mcp

# Local network - use server's LAN IP
codex mcp add --transport http rag-kb http://192.168.1.100:8000/mcp

# Verify connection
codex mcp list
```

**For VSCode users**: Restart VSCode after adding MCP server.

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
codex mcp remove rag-kb

# Step 2: Enable HTTP transport
codex --enable rmcp_client

# Step 3: Add HTTP server
codex mcp add --transport http rag-kb http://localhost:8000/mcp

# Step 4: Verify
codex mcp list
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
codex mcp add rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

---

## Installing Codex CLI

### Option 1: VSCode Extension (Recommended)

Install the [OpenAI Codex extension](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt) inside VSCode:

- Open VSCode → Extensions → search for "OpenAI Codex (ChatGPT)" → Install
- The extension provides a built-in chat interface
- CLI is bundled with the extension

### Option 2: Surface the VSCode Binary on Your PATH

```bash
# Find the latest extension folder
CODEX_BIN=$(ls -d ~/.vscode/extensions/openai.chatgpt-*/bin/linux-x86_64/codex | tail -n 1)

# Copy to PATH
sudo cp "$CODEX_BIN" /usr/local/bin/codex
sudo chmod 755 /usr/local/bin/codex

# Verify
codex --version
```

---

## Verify Installation

```bash
codex mcp list
# Should show: rag-kb - Connected
```

**In VSCode**: Open Codex side panel → gear icon → MCP settings → confirm `rag-kb` is connected.

**In Codex chat**: Type `/mcp` to list tools.

---

## Network Scenarios

### Scenario 1: Same Machine (localhost)

```
[Your Computer]
├── Codex CLI / VSCode
└── Docker (rag-api on port 8000)

URL: http://localhost:8000/mcp
```

### Scenario 2: Local Network (LAN)

```
[Your Laptop]                    [Desktop Server]
├── Codex CLI / VSCode     →     └── Docker (rag-api)
                                     IP: 192.168.1.100

URL: http://192.168.1.100:8000/mcp
```

### Scenario 3: Remote/Internet

```
[Your Laptop]                    [Remote Server]
├── Codex CLI / VSCode     →     └── Docker (rag-api)
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

## Manual Config (config.toml)

If CLI doesn't work, edit `~/.codex/config.toml` directly:

**HTTP Transport (recommended):**
```toml
[features]
rmcp_client = true

[mcp_servers.rag-kb]
url = "http://localhost:8000/mcp"
```

**For remote server:**
```toml
[features]
rmcp_client = true

[mcp_servers.rag-kb]
url = "http://192.168.1.100:8000/mcp"
```

**stdio Transport (legacy):**
```toml
[mcp_servers.rag-kb]
command = "node"
args = ["/absolute/path/to/rag-kb/mcp-server/index.js"]

[mcp_servers.rag-kb.env]
RAG_API_URL = "http://localhost:8000"
```

---

## Troubleshooting

### MCP Not Connecting

```bash
# 1. Check RAG is running
curl http://localhost:8000/health

# 2. Check MCP endpoint
curl http://localhost:8000/mcp

# 3. Check MCP status
codex mcp list

# 4. If "Failed to connect" - remove and re-add
codex mcp remove rag-kb
codex mcp add --transport http rag-kb http://localhost:8000/mcp
```

### HTTP vs stdio Comparison

| Feature | HTTP (Recommended) | stdio (Legacy) |
|---------|-------------------|----------------|
| **Setup** | Simple (one command) | Requires Node.js |
| **Dependencies** | Docker only | Docker + Node.js |
| **Remote access** | Direct URL | SSH tunnel or local |
| **Use case** | All scenarios | Backwards compatibility |

---

## See Also

- [MCP_CLAUDE.md](MCP_CLAUDE.md) - Claude Code setup
- [MCP_GEMINI.md](MCP_GEMINI.md) - Google Gemini setup
- [MCP_NETWORK.md](MCP_NETWORK.md) - Network configuration details
- [USAGE.md](USAGE.md) - Query methods

---

## References

- [Codex MCP Documentation](https://developers.openai.com/codex/mcp/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

Sources:
- [Codex Streamable HTTP PR](https://github.com/openai/codex/pull/4317)
- [Codex MCP Config Guide](https://vladimirsiedykh.com/blog/codex-mcp-config-toml-shared-configuration-cli-vscode-setup-2025)
