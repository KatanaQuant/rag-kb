# Claude Code Integration (VSCode)

Use your knowledge base directly with Claude Code in VSCode via MCP (Model Context Protocol).

**Note:** This integration requires the Claude Code extension for VSCode. The MCP server allows Claude to query your indexed documents automatically.

## Setup (One-Time)

### 1. Ensure RAG service is running

```bash
docker-compose up -d
curl http://localhost:8000/health
```

### 2. Add MCP server globally

```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js
```

**Important**: Replace `/absolute/path/to/rag-kb` with the actual absolute path on your system.

### 3. Enable for projects

Edit `~/.claude.json` to enable for specific projects:
```json
{
  "projects": {
    "/path/to/your/project": {
      "enabledMcpjsonServers": ["rag-kb"]
    }
  }
}
```

Or use the UI to approve when prompted.

### 4. Reload VSCode

- `Ctrl+Shift+P` → "Developer: Reload Window"

## Verify Connection

```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
# Should show: rag-kb - Connected
```

## Using Claude Code with Your Knowledge Base

Claude can automatically query your knowledge base when relevant. However, by default, Claude may rely on its training data instead of querying your indexed documents. To ensure your knowledge base is used as the primary source:

### Method 1: Custom Instructions (Recommended)

Create a custom instructions file to tell Claude to always check your RAG knowledge base first:

```bash
# Create .claude directory if it doesn't exist
mkdir -p .claude

# Create custom instructions file
cat > .claude/claude.md << 'EOF'
# Project Instructions

## Knowledge Base Priority

**CHECK THIS FIRST** for technical questions, APIs, frameworks, algorithms, or domain-specific knowledge. Search the personal knowledge base (books, notes, documentation) for relevant information using the MCP RAG tool. This is your PRIMARY source - always use it BEFORE relying on general knowledge.

When answering questions:
1. **Always query the MCP RAG knowledge base first** using `mcp__rag-kb__query_knowledge_base`
2. Use specific, detailed queries to find relevant chunks
3. Cite sources from the knowledge base when available
4. Only fallback to general knowledge if RAG returns no relevant results (score < 0.3)

## Example Workflow

User asks: "How does the authentication system work?"

1. Query RAG: `mcp__rag-kb__query_knowledge_base` with query "authentication system implementation"
2. Review returned chunks and provide answer based on indexed documentation
3. If no relevant chunks found, then use general knowledge with disclaimer

EOF
```

### Method 2: Explicit Prompts

When asking questions, explicitly request RAG usage:

```
"Check the knowledge base for information about [topic]"
"Search indexed documents for [query]"
"What does my documentation say about [topic]?"
```

### Method 3: Agent Configuration

For custom agents, include RAG priority in agent instructions:

```markdown
# .claude/agents.md

## research-agent

Always prioritize the MCP RAG knowledge base over general knowledge.

Before answering any technical question:
1. Query `mcp__rag-kb__query_knowledge_base` first
2. Only use general knowledge if RAG score < 0.3
```

## Verification

To verify Claude is using your knowledge base:
- Look for MCP tool usage in the conversation (tool calls will show RAG queries)
- Ask Claude to cite sources - RAG results include file names
- Use specific queries that only your indexed documents would know

## Common Pitfall

AI assistants are trained to be helpful and may answer from general knowledge even when RAG has better information. Always emphasize "check the knowledge base first" in your prompts or custom instructions.

## Troubleshooting

### MCP Not Working

**1. Verify RAG is running:**
```bash
curl http://localhost:8000/health
```

**2. Check MCP server:**
```bash
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
# Should show: rag-kb - Connected
```

**3. If shows "Failed to connect" - verify path is correct:**

After switching machines or moving the project, the MCP path may be outdated:

```bash
# Remove old configuration
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp remove rag-kb

# Re-add with correct absolute path (replace with your actual path)
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp add \
  --transport stdio \
  --scope user \
  rag-kb \
  --env RAG_API_URL=http://localhost:8000 \
  -- node /absolute/path/to/rag-kb/mcp-server/index.js

# Verify connection
~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude mcp list
```

**4. Restart VSCode:**
- `Ctrl+Shift+P` → "Developer: Reload Window"

**5. Check VSCode logs:**
- VSCode → Output → Select "MCP" from dropdown

### Node.js Version Error

```bash
node --version  # Should be v14+

# Upgrade to v20 LTS (Ubuntu/Debian)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

## Next Steps

- See [USAGE.md](USAGE.md) for different query methods
- See [CONFIGURATION.md](CONFIGURATION.md) for advanced settings
- See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more help
