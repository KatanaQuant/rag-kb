# MCP Network Setup Guide

Network-accessible MCP server for RAG Knowledge Base using HTTP transport.

## Overview

This guide shows how to access your RAG knowledge base from any device on your local network using the MCP HTTP endpoint.

**Use Cases:**
- Access your knowledge base from laptop → desktop server
- Multiple clients connecting to single knowledge base
- Docker container accessible from host machine
- Future: Internet access with authentication (enterprise feature)

## Architecture

**Two MCP Transport Options:**

1. **HTTP** (recommended) - Network communication
   - For: All clients (local and remote)
   - Protocol: Streamable HTTP (JSON-RPC 2.0 + SSE)
   - Location: `api/routes/mcp.py` (FastAPI endpoint)
   - Endpoint: `http://your-server:8000/mcp`
   - **No Node.js required** - direct connection to Docker

2. **stdio** (legacy) - Local process communication
   - For: Backwards compatibility
   - Protocol: stdio (stdin/stdout)
   - Location: `mcp-server/index.js`
   - Requires: Node.js + local server

Both transports use the same RAG API backend and expose identical tools.

## Features

**Available Tools:**
1. `query_kb` - Semantic search across documents
2. `list_indexed_documents` - List all indexed files
3. `get_kb_stats` - Knowledge base statistics

**Protocol:** MCP Streamable HTTP (spec: 2025-03-26)
- JSON-RPC 2.0 for requests
- SSE (Server-Sent Events) for streaming responses
- No authentication (local network only)

## Setup

### 1. Start RAG API

The MCP HTTP endpoint is part of the FastAPI server:

```bash
docker-compose up -d
```

Verify API is running:

```bash
curl http://localhost:8000/health
```

### 2. Find Your Server IP

**On Linux:**
```bash
ip addr show | grep "inet " | grep -v 127.0.0.1
```

**On macOS:**
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Example output: `192.168.1.100`

### 3. Test MCP Endpoint

**Get server info:**
```bash
curl http://YOUR_SERVER_IP:8000/mcp
```

**Example response:**
```json
{
  "name": "rag-kb-http",
  "version": "1.0.0",
  "protocol": "MCP Streamable HTTP",
  "transport": "HTTP + SSE",
  "authentication": "none (local network only)",
  "tools": [
    "query_kb",
    "list_indexed_documents",
    "get_kb_stats"
  ],
  "endpoint": "/mcp"
}
```

### 4. Configure MCP Client

**Client Configuration Example:**

```json
{
  "mcpServers": {
    "rag-kb-network": {
      "url": "http://192.168.1.100:8000/mcp",
      "transport": "http"
    }
  }
}
```

## Testing with curl

### Initialize Session

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }'
```

### List Available Tools

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }'
```

### Query Knowledge Base

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "query_kb",
      "arguments": {
        "query": "refactoring techniques",
        "top_k": 5
      }
    }
  }'
```

### Get Knowledge Base Stats

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "get_kb_stats",
      "arguments": {}
    }
  }'
```

### List Indexed Documents

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "list_indexed_documents",
      "arguments": {}
    }
  }'
```

## Network Configuration

### Docker Port Mapping

The `docker-compose.yml` already exposes port 8000:

```yaml
services:
  rag-api:
    ports:
      - "8000:8000"
```

This makes the MCP endpoint accessible at:
- **From host:** `http://localhost:8000/mcp`
- **From LAN:** `http://YOUR_SERVER_IP:8000/mcp`

### Firewall Configuration

If you can't connect from other devices, check your firewall:

**Linux (ufw):**
```bash
sudo ufw allow 8000/tcp
```

**Linux (firewalld):**
```bash
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --reload
```

**macOS:**
System Preferences → Security & Privacy → Firewall → Firewall Options → Allow port 8000

## Security Considerations

### Current Setup (Local Network Only)

- No authentication required
- Suitable for trusted local networks (home, office LAN)
- Fast and simple
- WARNING: Do NOT expose to internet without authentication

### Future: Enterprise Authentication (v2.0+)

Planned features for internet access:
- OAuth 2.1 authentication
- API key management
- Rate limiting
- Multi-tenant support

Deferred until post-GPU infrastructure (when enterprise features become valuable).

## Troubleshooting

### Connection Refused

**Check if API is running:**
```bash
docker ps | grep rag-api
```

**Check if port is listening:**
```bash
sudo netstat -tlnp | grep :8000
```

### Can't Connect from Other Devices

1. **Check firewall** (see Firewall Configuration above)
2. **Verify server IP:**
   ```bash
   ip addr show
   ```
3. **Test from server first:**
   ```bash
   curl http://localhost:8000/mcp
   ```
4. **Test from client:**
   ```bash
   curl http://SERVER_IP:8000/mcp
   ```

### MCP Endpoint Not Found

If you get 404 on `/mcp`:

1. **Check API version:**
   ```bash
   curl http://localhost:8000/health
   ```
   Should show the MCP endpoint is registered.

2. **Restart Docker container:**
   ```bash
   docker-compose restart rag-api
   ```

## Comparison: stdio vs HTTP

| Feature | stdio MCP | HTTP MCP |
|---------|-----------|----------|
| **Transport** | stdin/stdout | HTTP + SSE |
| **Network** | Same machine only | Local network / Internet |
| **Clients** | One per process | Multiple concurrent |
| **Latency** | ~1ms | ~5-10ms (LAN) |
| **Use Case** | Claude Desktop local | Laptop → Server |
| **Auth** | Process isolation | None (local) / OAuth (future) |
| **Setup** | Node.js process | API endpoint |

## API Reference

### Endpoints

**GET /mcp**
- Returns server info and capabilities
- No authentication required

**POST /mcp**
- Accepts JSON-RPC 2.0 requests
- Returns JSON or SSE stream
- Content-Type: `application/json`
- Accept: `application/json, text/event-stream`

### JSON-RPC Methods

**initialize**
- Initialize MCP session
- Returns: Server capabilities and protocol version

**tools/list**
- List available tools
- Returns: Array of tool definitions

**tools/call**
- Call a tool with arguments
- Returns: Tool result (text content)

### Response Format

**JSON Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { ... }
}
```

**SSE Response:**
```
data: {"jsonrpc":"2.0","id":1,"result":{...}}

```

**Error Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Internal error: ..."
  }
}
```

## Implementation Details

### Code Location

```
api/
├── routes/
│   └── mcp.py           # HTTP MCP endpoint (JSON-RPC + SSE)
├── operations/
│   ├── query_executor.py    # Query execution
│   └── document_lister.py   # Document listing
└── main.py              # Router registration

mcp-server/
└── index.js             # stdio MCP server (existing)
```

### Protocol Specification

- **MCP Version:** 2024-11-05 (stable)
- **Transport:** Streamable HTTP
- **Spec:** https://modelcontextprotocol.io/specification/2025-03-26/basic/transports

### Why Streamable HTTP?

The MCP spec updated in March 2025 to use "Streamable HTTP" which replaces the older "HTTP+SSE" pattern:

- **Old (deprecated):** HTTP POST for client→server, SSE for server→client
- **New (current):** Single HTTP endpoint supporting both JSON and SSE responses

Benefits:
- Simpler client implementation
- Better proxy compatibility
- Easier to deploy in enterprise environments

## What's Next

### Planned Improvements

**v1.9.x (Current):**
- HTTP MCP endpoint validated with Claude Code
- Local network access (no auth)
- JSON-RPC 2.0 compliance verified

**v2.0.0+ (GPU Infrastructure):**
- OAuth 2.1 authentication
- Internet access with proper security
- Multi-tenant support
- Rate limiting and quotas

**Enterprise (Post-GPU):**
- SSO integration
- Audit logging
- Usage analytics
- SLA guarantees

## Related Documentation

- [MCP_CLAUDE.md](MCP_CLAUDE.md) - Claude Code setup (HTTP recommended)
- [MCP_CODEX.md](MCP_CODEX.md) - Cursor (Codex AI) setup
- [MCP_GEMINI.md](MCP_GEMINI.md) - Gemini Code Assist setup
- [MCP_AMP.md](MCP_AMP.md) - Amp VSCode extension setup
- [ROADMAP.md](ROADMAP.md) - Project roadmap and future plans

## Support

For issues or questions:
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- File an issue on GitHub
- Review MCP specification: https://modelcontextprotocol.io/

---

**Version:** 1.1.0 (v1.9.x)
**Last Updated:** 2025-11-30
**Status:** Validated with Claude Code
