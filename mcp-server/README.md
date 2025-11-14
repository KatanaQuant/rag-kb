# RAG Knowledge Base MCP Server

MCP (Model Context Protocol) server that integrates your local RAG knowledge base with Claude Code.

## Features

**3 Tools Available to Claude:**

1. **`query_knowledge_base`** - Search your knowledge base
   - Semantic search across all your documents
   - Returns top-k most relevant chunks
   - Adjustable similarity threshold

2. **`list_indexed_documents`** - See what's in your knowledge base
   - Lists all indexed files
   - Shows chunk counts and index dates

3. **`get_kb_stats`** - Knowledge base health check
   - Total documents and chunks
   - Model information
   - System status

## Setup

### 1. Install Dependencies

```bash
cd mcp-server
npm install
```

### 2. Configure Claude Code

Add to your Claude Code MCP settings (`~/.config/claude-code/mcp.json` or via UI):

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

**Note:** Replace `/absolute/path/to/rag-kb/` with your actual installation path.

### 3. Restart Claude Code

The MCP server will start automatically when Claude Code launches.

## Usage

Claude Code will automatically use these tools when relevant:

**Example conversations:**

```
You: "What does my refactoring guide say about god objects?"
Claude: [Calls query_knowledge_base("god objects")]
Claude: "According to your refactoring guide (sample-refactoring-guide.md),
        God Objects are anti-patterns where..."

You: "What documents do I have indexed?"
Claude: [Calls list_indexed_documents()]
Claude: "You have 2 documents indexed:
        - sample-refactoring-guide.md (4 chunks)
        - README.md (2 chunks)"

You: "Is my knowledge base working?"
Claude: [Calls get_kb_stats()]
Claude: "Your knowledge base is healthy with 2 documents
        and 6 chunks indexed using all-MiniLM-L6-v2"
```

## Configuration

### Environment Variables

- `RAG_API_URL` - URL of your RAG API (default: `http://localhost:8000`)

### Custom Port

If your RAG API runs on a different port:

```json
{
  "mcpServers": {
    "rag-kb": {
      "command": "node",
      "args": ["/path/to/mcp-server/index.js"],
      "env": {
        "RAG_API_URL": "http://localhost:8001"
      }
    }
  }
}
```

## Troubleshooting

### MCP Server Not Working

1. **Check RAG API is running:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Check MCP server logs:**
   - Look in Claude Code's MCP server logs
   - Or run manually: `node index.js` (it should wait for stdio input)

3. **Verify path in config:**
   - Use absolute paths in `mcp.json`
   - Ensure `node` is in your PATH

### Claude Not Using Tools

- Make sure you restarted Claude Code after adding MCP config
- Check Claude Code settings to verify MCP server is connected
- Try explicitly asking: "Search my knowledge base for X"

## Development

Test the tools manually:

```bash
# Query knowledge base
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your query", "top_k": 5}'

# List documents
curl http://localhost:8000/documents

# Get stats
curl http://localhost:8000/health
```

## How It Works

1. Claude Code spawns this MCP server via Node.js
2. Server exposes 3 tools to Claude
3. When Claude needs knowledge, it calls `query_knowledge_base`
4. MCP server forwards request to your local RAG API
5. Results are formatted and returned to Claude
6. Claude incorporates the knowledge into its response

**Zero manual intervention needed!**
