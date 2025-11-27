# MCP Integration (Claude Code)

Use your knowledge base with Claude Code via MCP (Model Context Protocol).

> **Other AI Assistants**: See [MCP_CODEX.md](MCP_CODEX.md) for OpenAI Codex or [MCP_GEMINI.md](MCP_GEMINI.md) for Google Gemini.
>
> **Note**: This file was previously named `MCP_INTEGRATION.md`.

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

3. Claude CLI installed (see next section)

---

## Installing Claude CLI

Choose based on your setup:

### Option 1: VSCode Extension (Recommended for IDE users)

Install the [Claude Code extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) from VSCode marketplace. The extension bundles its own CLI binary.

After installation, the `claude` command is available in VSCode's integrated terminal.

### Option 2: Surface the VSCode Binary on Your PATH

If you have the VSCode extension but want `claude` available from any shell (not just VSCode's integrated terminal):

```bash
# Find the extension's bundled binary
CLAUDE_BIN=$(ls ~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude | tail -n 1)

# Copy or symlink to PATH
sudo cp "$CLAUDE_BIN" /usr/local/bin/claude
sudo chmod 755 /usr/local/bin/claude

# Verify
claude --version
```

**Alternative**: Call the binary directly without copying:
```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
```

Repeat the copy whenever the extension updates.

### Option 3: Native Installer (Terminal-only users)

For users who prefer terminal without VSCode:

```bash
# Install via native installer (recommended)
curl -fsSL https://claude.ai/install.sh | bash

# Verify installation
claude --version

# Authenticate
claude auth login
```

**Alternative (npm):** If the native installer doesn't work:
```bash
npm install -g @anthropic-ai/claude-code
```

---

## Setup via CLI (Recommended)

The Claude CLI handles configuration reliably. Manual JSON editing often fails.

### Option A: Global Install (All Projects)

```bash
claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

This installs RAG-KB globally for all projects.

### Option B: Project-Specific Install

```bash
claude mcp add \
  --transport stdio \
  --scope project \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

This installs RAG-KB only for the current project directory.

**Important**: Replace `/absolute/path/to/rag-kb` with your actual path.

### Verify Installation

```bash
claude mcp list
# Should show: rag-kb - Connected
```

**For VSCode users**: Reload window after adding MCP server:
`Ctrl+Shift+P` → "Developer: Reload Window"

**For terminal users**: The MCP server is available immediately in new `claude` sessions.

### Enable in the VSCode Extension

1. After running `claude mcp add ...`, reload VSCode: `Ctrl+Shift+P` → "Developer: Reload Window"
2. Open a new Claude Code chat session.
3. Type `/mcp` to verify `rag-kb` is connected and tools are available.

---

## Alternative: Manual Config (~/.claude.json)

If CLI doesn't work, edit `~/.claude.json` directly:

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

---

## Enable for Projects (Global Install Only)

If you used `--scope user` (global), enable for specific projects:

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

---

## Usage

### In VSCode (Extension)

Claude automatically has access to MCP tools. Ask questions naturally - Claude decides when to query your knowledge base.

### In Terminal (CLI)

Start an interactive session:
```bash
claude
```

Or run a single query:
```bash
claude "What does my knowledge base say about [topic]?"
```

Use `/mcp` command to see available tools:
```
/mcp
```

---

## Making the Assistant Prioritize Your KB

By default, AI assistants may answer from training data. To prioritize your knowledge base:

### Option 1: Project Instructions (Recommended)

Create a project instructions file (`.claude/claude.md` for Claude, or equivalent for other assistants):

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

### Claude CLI Not Found

**VSCode users**: Use the integrated terminal (not external terminal).

**Terminal users**: Verify installation:
```bash
which claude
claude --version

# If not found, reinstall:
npm install -g @anthropic-ai/claude-code
```

### MCP Not Connecting

```bash
# 1. Check RAG is running
curl http://localhost:8000/health

# 2. Check MCP status
claude mcp list

# 3. If "Failed to connect" - remove and re-add
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

- [MCP_CODEX.md](MCP_CODEX.md) - OpenAI Codex setup
- [MCP_GEMINI.md](MCP_GEMINI.md) - Google Gemini setup
- [USAGE.md](USAGE.md) - Query methods
- [CONFIGURATION.md](CONFIGURATION.md) - Settings
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - More help

---

## References

- [Claude Code Documentation](https://docs.anthropic.com/claude-code)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
