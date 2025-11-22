# Quick Start Guide

This guide will get you up and running with RAG-KB in under 5 minutes.

## Prerequisites

- **Docker** and **Docker Compose**
- **Node.js v14+** (for MCP server - optional)
- **Git**

## Step 0: Clone Repository

```bash
# Clone the repository
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb

# Checkout latest stable release
git checkout v0.11.0-alpha

# Optional: Change port if 8000 is in use
echo "RAG_PORT=8001" > .env

# Optional: Use faster model for English-only content (recommended)
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" >> .env
```

## Step 1: Add Content

The `knowledge_base/` directory is where you put your documents and code. It's **gitignored by default** to protect your personal/copyrighted content.

### Add Documents

```bash
# Create organization structure (optional)
mkdir -p knowledge_base/{books,notes,docs,papers}

# Add some content
cp ~/Documents/my-book.pdf knowledge_base/books/
cp ~/Documents/*.md knowledge_base/docs/
cp ~/notes/*.txt knowledge_base/notes/
```

### Add Codebases (v0.8.0+)

Same simple workflow - just drop repos into `knowledge_base/`:

```bash
cd knowledge_base
git clone https://github.com/anthropics/anthropic-sdk-python.git

# Or copy your own projects
cp -r ~/projects/my-trading-bot ./my-trading-bot
```

The system automatically:
- Routes `.py`, `.ts`, `.java`, `.cs`, `.go` files → AST-based chunking (respects function/class boundaries)
- Routes `.md`, `.pdf`, `.epub` files → Document extraction with Docling
- Skips `.git/`, `node_modules/`, `__pycache__/`, `.env` files, build artifacts, etc.

**Query Example**: "How does the SDK handle API retries?"
- Returns: `retry.py` implementation + README.md docs + related code

The service automatically indexes all supported files when it starts.

**Note:** Your content stays local and private - it's never committed to git.

## Step 2: Start the Service

```bash
# Build and start
docker-compose up --build -d

# Wait ~30 seconds for indexing (longer for large knowledge bases)
# Check status
curl http://localhost:8000/health
```

**Expected output:**
```json
{
  "status": "healthy",
  "indexed_documents": 15,
  "total_chunks": 1234,
  "model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

## Step 3: Test a Query

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "What is machine learning?", "top_k": 3}'
```

## Next Steps

- **MCP Integration**: See [CLAUDE_CODE_INTEGRATION.md](CLAUDE_CODE_INTEGRATION.md) to use with Claude Code in VSCode
- **Usage Patterns**: See [USAGE.md](USAGE.md) for different query methods
- **Configuration**: See [CONFIGURATION.md](CONFIGURATION.md) for advanced settings
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if you encounter issues

## Performance Notes

> **CPU-Only Build**: This project is optimized exclusively for CPU processing. No GPU required or supported. Large knowledge bases may take significant time to index:
>
> - **Small KB** (10-50 docs): Minutes to hours
> - **Medium KB** (100-500 docs): Hours to overnight
> - **Large KB** (500+ docs): Days to weeks
>
> **Performance Recommendation**: For English-only content, use `sentence-transformers/static-retrieval-mrl-en-v1` model for 100-400x faster processing with minimal quality trade-off. See [CONFIGURATION.md](CONFIGURATION.md#embedding-models) for details.
