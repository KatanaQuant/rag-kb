# Release Notes: v0.9.0-alpha

**Release Date:** 2025-11-19
**Focus:** Jupyter Notebook Support + Obsidian Graph-RAG

## Overview

Version 0.9.0-alpha adds two major content processing capabilities: cell-aware Jupyter notebook chunking and full Graph-RAG architecture for Obsidian vaults.

## New Features

### 1. Jupyter Notebook Support (Cell-Aware Chunking)

**What:** Intelligent processing of `.ipynb` files with cell-level granularity and AST-based code chunking.

**Key Features:**
- Cell-aware chunking preserves notebook structure (code cells, markdown cells, outputs)
- AST chunking for code cells using tree-sitter (Python, R, Julia, JavaScript, etc.)
- Markdown cells processed with semantic awareness
- Output preservation (text, images, tables, errors)
- 160+ programming languages supported via tree-sitter-language-pack
- Fallback to line-based chunking for unsupported languages

**Technical Details:**
- New `JupyterExtractor` class ([api/ingestion/jupyter_extractor.py](../api/ingestion/jupyter_extractor.py))
- Reads notebooks via `nbformat` (official Jupyter format library)
- Integrates with existing `TreeSitterChunker` for code
- Preserves cell metadata and execution order

**Example Use Cases:**
- Index data science notebooks for analysis workflow reference
- Search across computational research documentation
- Find code patterns in educational Jupyter content

### 2. Obsidian Vault Support (Graph-RAG)

**What:** Full Graph-RAG implementation for Obsidian personal knowledge bases with bidirectional linking.

**Architecture:**
```
Obsidian Vault → Graph Construction → Semantic Chunking → Graph Enrichment → Database Persistence
```

**Key Features:**
- **Knowledge Graph Construction:** NetworkX-based graph with 4 node types (notes, tags, headers, note_refs) and 4 edge types (wikilinks, backlinks, tags, header hierarchies)
- **Smart Detection:** Automatic Obsidian vault detection via `.obsidian` folder and content heuristics
- **Semantic Chunking:** Header-aware markdown chunking with 2048-char max and 200-char overlap
- **Graph Enrichment:** Each chunk enhanced with graph metadata footer (tags, wikilinks, backlinks, related notes)
- **Multi-Hop Traversal:** N-hop neighbor discovery for context expansion
- **Smart Cleanup:** Reference counting for shared resources (tags persist if other notes reference them)
- **Database Persistence:** 4 new tables for graph storage with graceful migration

**Graph Schema:**
```
Nodes:
  - note: Main note documents
  - tag: Hashtags (#tag)
  - header: Document headers (H1, H2, H3, etc.)
  - note_ref: Wikilink placeholders for non-existent notes

Edges:
  - wikilink: [[Note A]] → [[Note B]]
  - backlink: Reverse of wikilink
  - tag: Note → #tag
  - header_child: Header hierarchy (H1 → H2 → H3)
```

**New Components:**
- `ObsidianGraphBuilder` - NetworkX graph construction ([api/ingestion/obsidian_graph.py](../api/ingestion/obsidian_graph.py))
- `ObsidianExtractor` - Semantic chunking + enrichment ([api/ingestion/obsidian_extractor.py](../api/ingestion/obsidian_extractor.py))
- `ObsidianDetector` - Vault/note detection ([api/ingestion/obsidian_detector.py](../api/ingestion/obsidian_detector.py))
- `GraphRepository` - Database CRUD operations ([api/ingestion/graph_repository.py](../api/ingestion/graph_repository.py))

**Graph Enrichment Example:**
```markdown
---
Note: Risk Premia Harvesting
Tags: #Equal, #Risk, #Rolling, #strategy
Links to: Risk Premium, Diversification, Volatility Targeting (+13 more)
Related notes: Systematic Trading, Rebalancing, Portfolio Optimization...
```

**Database Schema:**
```sql
-- New tables (gracefully added, no migration needed)
graph_nodes (node_id, node_type, title, content, metadata)
graph_edges (id, source_id, target_id, edge_type, metadata)
graph_metadata (node_id, pagerank_score, in_degree, out_degree)
chunk_graph_links (chunk_id, node_id, link_type)
```

**Smart Cleanup on Reindex:**
- Note-specific nodes (note, headers) deleted immediately
- Shared nodes (tags) only deleted when no references remain
- SQL reference counting prevents orphans
- CASCADE deletion handles edges automatically

**Test Coverage:**
- 9 comprehensive TDD test cases ([api/tests/test_obsidian_graph_cleanup.py](../api/tests/test_obsidian_graph_cleanup.py))
- Tests cover: node deletion, tag persistence, edge cleanup, renames, headers, multi-note scenarios

## Technical Improvements

### Hash-Based File Tracking
- File identity now tracked by content hash instead of path
- Reorganizing files in knowledge_base no longer triggers reindexing
- System detects file moves vs duplicates:
  - If original path missing: File moved, update path without reindex
  - If original path exists: Duplicate file with same content, skip it
- Two-step update process prevents UNIQUE constraint conflicts during file swaps
- Graph node paths automatically updated for Obsidian notes on file moves
- Implementation: [database.py:286-365](../api/ingestion/database.py#L286-L365)

### Smart Markdown Routing
- `TextExtractor` now intelligently routes `.md` files:
  - Obsidian notes → `ObsidianExtractor` (Graph-RAG)
  - Regular markdown → `MarkdownExtractor` (Docling)
- Detection via `.obsidian` folder OR content heuristics (wikilinks, tags, frontmatter)

### Database Migration
- Graceful schema addition with `CREATE TABLE IF NOT EXISTS`
- Existing data preserved (documents, chunks, vectors)
- No manual migration required

### Docker Resource Configuration
- Increased default resource limits: 12 CPUs, 22GB RAM
- Configurable via MAX_CPUS and MAX_MEMORY environment variables
- Enables faster processing on high-performance systems

### Dependencies
- Added `nbformat>=5.9.0` for Jupyter support
- Added `tree-sitter-language-pack>=0.10.0` for R and 160+ languages
- Added `obsidiantools>=0.10.0` for Obsidian parsing
- Added `networkx>=3.0` for graph construction

## Statistics

### Test Vault (Obsidian)
- **120 graph nodes:** 19 notes, 32 headers, 12 tags, 57 note_refs
- **262 graph edges:** 102 wikilinks, 102 backlinks, 26 tag links, 32 header hierarchies
- **17 documents** indexed with **64 chunks**

### Performance
- Graph persistence: Sub-second for typical vaults (<100 notes)
- Hybrid search benefits from enriched metadata
- No performance degradation on existing content types

## Known Issues

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for detailed tracking.

**Relevant to this release:**
- TextExtractor naming is misleading (router/coordinator behavior) - cosmetic issue, low priority

## Compatibility

### Supported Content Types
- PDF documents (Docling + HybridChunker)
- EPUB ebooks (Pandoc → Docling)
- Markdown files (regular + Obsidian)
- Code files (Python, Java, TypeScript, C#, JavaScript, etc. with AST chunking)
- Jupyter notebooks (cell-aware + AST chunking) - NEW
- Obsidian vaults (Graph-RAG) - NEW

### Backward Compatibility
- All existing features unchanged
- Existing databases automatically upgraded
- No breaking changes to API

## Migration Guide

### From v0.8.x

1. **Pull latest code:**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Rebuild Docker (dependencies changed):**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

3. **Database auto-migration:**
   - Graph tables created automatically on startup
   - No manual SQL needed

4. **Add content:**
   - Place Jupyter notebooks in `knowledge_base/`
   - Place Obsidian vaults in `knowledge_base/obsidian/` (or anywhere with `.obsidian` folder)
   - System auto-detects and routes appropriately

### Testing

After migration, verify:
```bash
# Health check
curl http://localhost:8000/health

# Test query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your query here", "top_k": 5}'

# Check logs
docker logs rag-api | grep -E "obsidian_graph_rag|jupyter_ast|Graph persisted"
```

## Contributors

This release includes contributions from multiple development sessions focusing on Jupyter notebook support and Obsidian Graph-RAG architecture.

## Next Steps

Potential areas for future development:
- PageRank scoring for Obsidian notes
- Graph visualization API endpoints
- Jupyter cell execution state tracking
- Multi-vault support with vault-level isolation
- Graph-based query expansion

---

**Full Changelog:** v0.8.1-alpha...v0.9.0-alpha
**Documentation:** See [README.md](../README.md) for usage examples
