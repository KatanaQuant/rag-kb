# MCP Integration (Google Gemini)

Use your knowledge base with Google Gemini CLI via MCP.

> **Other AI Assistants**: See [MCP_CLAUDE.md](MCP_CLAUDE.md) for Claude Code or [MCP_CODEX.md](MCP_CODEX.md) for OpenAI Codex.
>
> **Note**: MCP support requires the standalone **Gemini CLI** (npm). The **Gemini Code Assist** VSCode extension uses a different binary (`cloudcode_cli`) that does not have MCP commands.

---

## Prerequisites

1. RAG service running:
   ```bash
   docker-compose up -d
   curl http://localhost:8000/health
   ```

2. Node.js v14+ installed:
   ```bash
   node --version
   ```

3. Gemini CLI installed (see next section)

---

## Installing Gemini CLI

The Gemini CLI is required for MCP configuration.

### Option 1: npm Install (Required for MCP)

```bash
# Install globally
npm install -g @google/gemini-cli

# Verify installation
gemini --version

# Authenticate
gemini  # First run will prompt for Google login
```

### Option 2: VSCode Extension (No MCP CLI)

The [Gemini Code Assist extension](https://marketplace.visualstudio.com/items?itemName=google.geminicodeassist) provides a built-in chat interface but bundles `cloudcode_cli` which does **not** have MCP commands.

- Install via VSCode Extensions → search "Gemini Code Assist"
- The extension can read MCP config from `~/.gemini/settings.json` (set up via npm CLI)
- Agent Mode is required to use MCP tools in VSCode

---

## Setup via CLI (Recommended)

The Gemini CLI handles configuration reliably.

### Option A: Global Install (All Projects)

```bash
gemini mcp add rag-kb \
  -e RAG_API_URL=http://localhost:8000 \
  -s user \
  node /absolute/path/to/rag-kb/mcp-server/index.js
```

### Option B: Project-Specific Install

```bash
gemini mcp add rag-kb \
  -e RAG_API_URL=http://localhost:8000 \
  -s project \
  node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

### Verify Installation

```bash
gemini mcp list
# Should show: ✓ rag-kb: node /path/to/mcp-server/index.js (stdio) - Connected
```

Use `/mcp` in an interactive `gemini` session to verify tools are available.

### Enable in the VSCode Extension

1. After running `gemini mcp add ...`, reload VSCode: `Ctrl+Shift+P` → "Developer: Reload Window"
2. Open Gemini Code Assist panel and enable **Agent Mode** (required for MCP).
3. In agent chat, verify `rag-kb` tools appear in the tool list.

**Note**: The VSCode extension reads `~/.gemini/settings.json` created by the npm CLI.

---

## Alternative: Manual Config (~/.gemini/settings.json)

If CLI doesn't work, edit `~/.gemini/settings.json` directly:

```json
{
  "mcpServers": {
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

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

### Configuration Locations

| Platform | Config File |
|----------|-------------|
| Gemini CLI | `~/.gemini/settings.json` |
| VSCode (Gemini Code Assist) | `~/.gemini/settings.json` |
| IntelliJ | `~/.config/JetBrains/<IDE>/mcp.json` |

Reload IDE after editing:
- **VSCode**: `Ctrl+Shift+P` → "Developer: Reload Window"
- **IntelliJ**: File → Invalidate Caches → Restart

---

## Gemini Code Assist: Agent Mode

Agent Mode is **required** to use MCP servers in VSCode:

1. Open Gemini Code Assist panel
2. Click the agent mode toggle (or use command palette: "Gemini: Enable Agent Mode")
3. MCP tools become available in agent conversations

Without Agent Mode, the extension operates as a regular chat without tool access.

---

## Usage

### In VSCode (Extension)

With Agent Mode enabled, Gemini automatically has access to MCP tools. Ask questions naturally.

### In Terminal (CLI)

Start an interactive session:
```bash
gemini
```

Use `/mcp` command to see available tools:
```
/mcp
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

## Making the Assistant Prioritize Your KB

By default, AI assistants may answer from training data. To prioritize your knowledge base:

### Option 1: Project Instructions (Recommended)

Create a project instructions file (e.g., `GEMINI.md` in project root):

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

Include in your prompts:
```
"Check my KB for information about [topic]"
"What do my docs say about [topic]?"
"Search the knowledge base first before answering"
```

---

## Troubleshooting

### Gemini CLI Not Found

```bash
which gemini
gemini --version

# If not found, reinstall:
npm install -g @google/gemini-cli
```

### MCP Server Not Available in Agent Mode

1. Verify Agent Mode is enabled (not regular chat)
2. Check `~/.gemini/settings.json` syntax (valid JSON)
3. Fully restart VSCode (not just reload window)
4. Check Gemini Code Assist version supports MCP

### "Command not found" Error

```bash
# Verify Node.js is in PATH
which node
node --version  # Requires v14+

# Use absolute path to node in config
{
  "mcpServers": {
    "rag-kb": {
      "command": "/usr/bin/node",
      "args": ["/path/to/mcp-server/index.js"]
    }
  }
}
```

### Connection Refused

```bash
# Verify RAG service is running
curl http://localhost:8000/health

# Check Docker container
docker-compose ps
docker-compose logs rag-api
```

### Remove and Re-add

```bash
gemini mcp remove rag-kb
gemini mcp add rag-kb \
  -e RAG_API_URL=http://localhost:8000 \
  -s user \
  node /absolute/path/to/rag-kb/mcp-server/index.js
```

---

## Security Note

MCP servers run with your user permissions. Only use servers from trusted sources.

---

## See Also

- [MCP_CLAUDE.md](MCP_CLAUDE.md) - Claude Code setup
- [MCP_CODEX.md](MCP_CODEX.md) - OpenAI Codex setup
- [USAGE.md](USAGE.md) - Query methods
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - More help

---

## References

- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)
- [Gemini CLI npm](https://www.npmjs.com/package/@google/gemini-cli)
- [Gemini Code Assist Agent Mode](https://developers.google.com/gemini-code-assist/docs/use-agentic-chat-pair-programmer)
