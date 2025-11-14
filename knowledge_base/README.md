# Knowledge Base Directory

This directory contains your personal knowledge base documents that will be indexed by the RAG system.

## Supported Formats

- **PDF** (`.pdf`) - Books, papers, documentation
- **DOCX** (`.docx`) - Word documents
- **Markdown** (`.md`, `.markdown`) - Notes, documentation
- **Plain Text** (`.txt`) - Any text content
- **Obsidian Vaults** - Exported via `ingest-obsidian.sh`

## Directory Structure

Organize your content however you like. Here's a recommended structure:

```
knowledge_base/
├── books/                    # Books and longer texts
│   ├── programming/
│   ├── design/
│   └── business/
├── code/                     # Exported codebases
│   ├── project1.md
│   └── project2.md
├── papers/                   # Research papers and articles
│   └── ml-papers/
├── notes/                    # Personal notes
│   ├── daily-notes/
│   └── project-notes/
└── obsidian/                 # Obsidian vault exports
    └── vault-export.md
```

## Example Content

### Books
- Technical books (POODR, Clean Code, etc.)
- Business books
- Domain-specific references

### Code
Export your repositories using the provided scripts:
```bash
./export-codebase.sh /path/to/repo > knowledge_base/code/myproject.md
```

### Notes
- Meeting notes
- Learning notes
- Project documentation
- How-to guides

### Papers
- Research papers
- Technical articles
- Blog posts (converted to markdown)

## Privacy Note

**This directory is gitignored by default** to prevent accidentally committing:
- Copyrighted material (books, papers)
- Proprietary code or information
- Personal notes and data

Only `.gitkeep` and this `README.md` are tracked in version control.

## Getting Started

1. **Add some content:**
   ```bash
   # Copy a book
   cp ~/Downloads/technical-book.pdf knowledge_base/books/

   # Export a codebase
   ./export-codebase.sh ~/projects/myapp > knowledge_base/code/myapp.md

   # Add your notes
   cp -r ~/Documents/notes/*.md knowledge_base/notes/
   ```

2. **Restart the service to index:**
   ```bash
   docker-compose restart rag-api
   ```

3. **Verify indexing:**
   ```bash
   curl http://localhost:8000/health
   # Check that indexed_documents count increased
   ```

4. **Query your knowledge base:**
   ```bash
   curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d '{"text": "your question here", "top_k": 5}'
   ```

## Tips

- **Start small:** Add a few documents first to test
- **Organize logically:** Use subdirectories that make sense to you
- **Monitor size:** Large PDFs take longer to process
- **Re-index after changes:** Restart the service when adding new files
- **Check logs:** `docker-compose logs -f rag-api` shows indexing progress

## Need Help?

See the main [README.md](../README.md) for:
- Full setup instructions
- Troubleshooting guide
- Advanced configuration
- Claude Code integration
