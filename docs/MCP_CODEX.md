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

   > Working inside a container or remote sandbox that blocks `localhost` can make this health check fail even when the service is running. When in doubt, exec into the `rag-api` container and run `curl` from there:
   > ```bash
   > docker-compose exec -T rag-api curl -s http://localhost:8000/health
   > ```

2. Node.js v14+ installed:
   ```bash
   node --version
   ```

3. Codex CLI installed (see next section).

---

## Installing Codex CLI

Choose the path that best matches your setup. Unlike Claude, Codex currently ships with the VSCode extension but does not publish an npm or Homebrew package.

### Option 1: VSCode Extension (Recommended for IDE users)

Install the [OpenAI Codex extension](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt) inside VSCode. The extension bundles the `codex` CLI:

- Open VSCode → Extensions → search for "OpenAI Codex (ChatGPT)" → Install.
- The extension provides a built-in chat interface (no CLI needed for basic usage).
- To use CLI features, see Option 2 to surface the binary on your PATH.

### Option 2: Surface the VSCode Binary on Your PATH

If you want `codex` available from any shell (outside VSCode), copy the bundled binary onto your system PATH:

```bash
# Find the latest extension folder
CODEX_BIN=$(ls -d ~/.vscode/extensions/openai.chatgpt-*/bin/linux-x86_64/codex | tail -n 1)

# Copy or symlink it somewhere on PATH
sudo cp "$CODEX_BIN" /usr/local/bin/codex
sudo chmod 755 /usr/local/bin/codex

# Example for version 0.4.46 if you prefer to be explicit:
sudo cp ~/.vscode/extensions/openai.chatgpt-0.4.46-linux-x64/bin/linux-x86_64/codex /usr/local/bin/codex
sudo chmod 755 /usr/local/bin/codex
```

Re-run `codex --version`. Repeat this copy whenever the extension updates to a new version.

> **FAQ**: There is no official `npm install codex` or PyPI/Homebrew release yet. Using the VSCode extension (and optionally copying its binary onto your PATH) is the supported way to obtain the CLI today.

---

## Setup via CLI (Recommended)

The Codex CLI handles configuration reliably.

### Option A: Global Install (Recommended)

Run this **from your host shell** so Codex can write to `~/.codex/config.toml`:

```bash
codex mcp add rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

### Option B: Extra Environment Variables

```bash
codex mcp add rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  --env NODE_ENV=production \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**:
- Replace `/absolute/path/to/rag-kb` with your actual path.
- If you need to test inside a sandbox that cannot write to your real home directory, temporarily override `HOME` (for example `HOME=$PWD/tmp-home codex mcp add ...`). Later, copy the generated `tmp-home/.codex/config.toml` contents into your real `~/.codex/config.toml`.

### Verify Installation

In Codex CLI (run `codex` interactively, then type):
```bash
/mcp
# Should show: rag-kb - Connected
```

From a non-interactive shell you can also check:
```bash
codex mcp list
codex mcp get rag-kb
```

In VSCode: Open the Codex side panel → click the gear icon → MCP settings → confirm `rag-kb` is `Connected`. A full VSCode restart is sometimes required after adding a new MCP server.

### Enable in the VSCode Extension

1. After running `codex mcp add ...`, restart VSCode.
2. Open the Codex view → Settings (gear) → MCP Settings.
3. Ensure `rag-kb` is toggled on. If it shows `Failed`, click the refresh icon or toggle off/on to reconnect.
4. Optional: in the Codex chat, type `/mcp` to list tools and verify `query_knowledge_base`, `list_indexed_documents`, and `get_kb_stats` appear.

---

## Alternative: Manual Config (config.toml)

If CLI doesn't work, edit `~/.codex/config.toml` directly:

```toml
[mcp_servers.rag-kb]
command = "node"
args = ["/absolute/path/to/rag-kb/mcp-server/index.js"]

[mcp_servers.rag-kb.env]
RAG_API_URL = "http://localhost:8000"
```

**Important**: Section must be `[mcp_servers.rag-kb]` (underscore, not hyphen).

---

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `command` | - | Command to launch server (stdio) |
| `args` | `[]` | Arguments for the command |
| `env` | `{}` | Environment variables |
| `startup_timeout_sec` | 10 | Server startup timeout |
| `tool_timeout_sec` | 60 | Tool execution timeout |
| `enabled` | true | Enable/disable without deletion |

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

Create a project instructions file (e.g., `AGENTS.md` or similar for Codex):

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

### MCP Not Detected in VSCode Extension

Known issue: MCP servers may work in CLI but not in VSCode extension.

**Workarounds:**
1. Fully restart VSCode (not just reload window)
2. Add startup timeout to config:
   ```toml
   [mcp_servers.rag-kb]
   startup_timeout_sec = 20
   ```
3. Check GitHub issues: [openai/codex#6465](https://github.com/openai/codex/issues/6465)

### Server Not Starting

```bash
# Test manually
RAG_API_URL=http://localhost:8000 node /path/to/rag-kb/mcp-server/index.js

# Check Node.js version (requires v14+)
node --version
```

### Connection Refused

```bash
# Verify RAG service is running
curl http://localhost:8000/health

# If localhost networking is blocked, exec into the container instead
docker-compose exec -T rag-api curl -s http://localhost:8000/health

# Check Docker container
docker-compose ps
docker-compose logs rag-api
```

### Remove and Re-add

```bash
codex mcp remove rag-kb
codex mcp add rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

### Let Codex (or Another Operator) Query Your KB

If you want this Codex agent (running inside the repo sandbox) to issue MCP queries for you:

1. Run all CLI steps above on your machine so `rag-kb` shows as `Connected` in `/mcp`.
2. Start an interactive Codex CLI session locally: `codex --full-auto` (or just `codex`).
3. Invite the agent to run `/mcp` commands by pasting:  
   ```
   /mcp query_knowledge_base {"query":"<your question>"}
   ```
   The agent’s output will now include the KB results pulled via your local MCP connection.
4. Share any relevant output or errors back here if we need to debug together.

---

## See Also

- [MCP_CLAUDE.md](MCP_CLAUDE.md) - Claude Code setup
- [MCP_GEMINI.md](MCP_GEMINI.md) - Google Gemini setup
- [USAGE.md](USAGE.md) - Query methods
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - More help

---

## References

- [Codex MCP Documentation](https://developers.openai.com/codex/mcp/)
- [Codex IDE Extension](https://developers.openai.com/codex/ide/)
