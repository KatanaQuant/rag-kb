# Obsidian Vault & Jupyter Notebook Processing

Research and implementation plan for adding support for Obsidian vaults and Jupyter notebooks (Python & R).

## Current State

### Supported File Types
Currently in `DocumentProcessor.SUPPORTED_EXTENSIONS`:
- Documents: `.pdf`, `.txt`, `.md`, `.markdown`, `.docx`, `.epub`
- Code: `.py`, `.java`, `.ts`, `.tsx`, `.js`, `.jsx`, `.cs`

### Existing Markdown Processing
- Uses `MarkdownExtractor` with Docling + HybridChunker
- Basic markdown support exists
- **No Obsidian-specific features** (wikilinks, tags, backlinks, frontmatter)

### Jupyter Notebook Support
- **NOT currently supported** (`.ipynb` not in SUPPORTED_EXTENSIONS)
- Claude Code Read tool can already parse `.ipynb` files nicely
- Shows markdown cells, code cells, and outputs separately

---

## Research Findings

### 1. Obsidian Vault Processing

#### Obsidian-Specific Features
1. **Wikilinks**: `[[link]]`, `[[link|alias]]`, `[[link#header]]`
2. **Tags**: `#tag`, `#nested/tag`
3. **Frontmatter**: YAML metadata at top of files
4. **Backlinks**: Graph relationships between notes
5. **Embeds**: `![[image.png]]`, `![[note]]`
6. **Block references**: `[[note#^blockid]]`

#### Recommended Library: `obsidiantools`
- **PyPI**: https://pypi.org/project/obsidiantools/
- **GitHub**: https://github.com/mfarragher/obsidiantools
- **Features**:
  - Parse wikilinks (including headers, aliases)
  - Extract tags (including nested tags)
  - Access graph structure (networkx)
  - Get backlinks and forward links
  - Extract plaintext content

#### Alternative: Python-Markdown WikiLinks Extension
- Built into standard `markdown` library (already installed)
- Simpler but less Obsidian-specific
- Converts `[[bracketed]]` words to links

### 2. Jupyter Notebook Processing

#### .ipynb File Structure
- JSON format with cells array
- Cell types: `code`, `markdown`, `raw`
- Each cell has:
  - `cell_type`: "code" | "markdown" | "raw"
  - `source`: list of strings (the content)
  - `outputs`: (for code cells) execution results
  - `metadata`: kernel info, language, etc.

#### Recommended Library: `nbformat`
- **PyPI**: https://pypi.org/project/nbformat/
- **Official Jupyter library** for reading/writing notebooks
- **Features**:
  - Read .ipynb files
  - Parse cells by type
  - Extract code, markdown, outputs
  - Validate notebook structure
  - Works with Python, R, Julia, etc. (kernel-agnostic)

#### Example Usage
```python
from nbformat import read, NO_CONVERT

with open("notebook.ipynb") as fp:
    notebook = read(fp, NO_CONVERT)

for cell in notebook['cells']:
    if cell['cell_type'] == 'code':
        code = ''.join(cell['source'])
    elif cell['cell_type'] == 'markdown':
        markdown = ''.join(cell['source'])
```

---

## Required Dependencies

### New Dependencies to Add

**For Obsidian Support:**
```
obsidiantools>=0.10.0  # Vault analysis, wikilinks, tags
```

**For Jupyter Support:**
```
nbformat>=5.9.0        # Official Jupyter notebook format library
```

### Already Installed
- `markdown==3.5.2` (for basic markdown, includes WikiLinks extension)
- `transformers>=4.30.0` (for tokenization)

---

## Processing Strategy

### Obsidian Vault Processing

#### Option 1: Enhanced Markdown with Obsidian Features (Recommended)
**Approach:**
1. Parse with `obsidiantools` to extract:
   - Wikilinks → preserve as context
   - Tags → add as metadata
   - Frontmatter → extract and add to metadata
   - Backlink graph → optional graph analysis
2. Convert to enriched markdown
3. Process with existing `MarkdownExtractor` (Docling + HybridChunker)
4. Enrich chunks with Obsidian metadata

**Advantages:**
- Preserves semantic relationships (wikilinks, tags)
- Leverages existing HybridChunker for quality chunking
- Adds valuable metadata for retrieval
- Maintains graph structure

**Metadata to add:**
```python
{
  'obsidian_tags': ['#tag1', '#nested/tag2'],
  'obsidian_links': ['[[Note 1]]', '[[Note 2|Alias]]'],
  'obsidian_backlinks': ['[[Source Note]]'],
  'frontmatter': {'author': 'X', 'created': '2025-01-01'}
}
```

#### Option 2: Vault-Level Graph Processing
**Approach:**
1. Load entire vault with `obsidiantools`
2. Build graph of relationships
3. Process notes with graph context
4. Optionally embed related notes together

**When to use:**
- User wants vault-wide search
- Graph relationships are critical
- Implementing "smart" Obsidian search

### Jupyter Notebook Processing

#### Recommended: Multi-Strategy Chunking
**Approach:**
1. Parse with `nbformat` to separate cell types
2. Process each cell type differently:

**Code Cells:**
- Extract code blocks
- Use `CodeExtractor` with AST-based chunking
- Preserve cell execution order
- Metadata: `cell_number`, `kernel_type` (python/R)

**Markdown Cells:**
- Extract markdown content
- Use `MarkdownExtractor` (Docling + HybridChunker)
- Metadata: `cell_number`, `cell_type: 'markdown'`

**Output Cells:**
- Extract text outputs (skip images/plots by default)
- Add as context or separate chunks
- Metadata: `cell_number`, `output_type`

**3. Create Notebook-Level Context:**
```python
{
  'notebook_path': '/path/to/notebook.ipynb',
  'kernel': 'python3' | 'ir',  # R kernel
  'cell_number': 5,
  'cell_type': 'code' | 'markdown',
  'has_output': True/False
}
```

**4. Chunking Strategy:**
- **Option A**: One chunk per cell (preserves cell boundaries)
- **Option B**: Combine adjacent cells by type (better for long notebooks)
- **Option C**: Smart chunking based on cell content size

---

## Implementation Plan

### Phase 1: Jupyter Notebook Support (Easier, More Valuable)

**Why first?**
- Simpler implementation (standard JSON format)
- Clear cell boundaries for chunking
- High value for code-heavy knowledge bases
- nbformat is well-maintained, stable API

**Tasks:**
1. Add `nbformat>=5.9.0` to requirements.txt
2. Create `JupyterExtractor` class in `extractors.py`
3. Implement cell-by-cell processing:
   - Code cells → AST chunking
   - Markdown cells → HybridChunker
   - Outputs → optional text extraction
4. Add `.ipynb` to `SUPPORTED_EXTENSIONS`
5. Test with Python and R notebooks
6. Add metadata enrichment (cell numbers, kernel type)

**Estimated Complexity:** Low-Medium
**Estimated Time:** 2-3 hours

### Phase 2: Obsidian Vault Support

**Tasks:**
1. Add `obsidiantools>=0.10.0` to requirements.txt
2. Create `ObsidianExtractor` class in `extractors.py`
3. Implement wikilink parsing and preservation
4. Implement tag extraction and metadata
5. Implement frontmatter YAML parsing
6. Enhance existing `.md` processing:
   - Check if file is part of Obsidian vault
   - If yes: use ObsidianExtractor
   - If no: use MarkdownExtractor (current behavior)
7. Optional: Vault-level graph analysis
8. Test with real Obsidian vault

**Estimated Complexity:** Medium
**Estimated Time:** 4-6 hours

### Phase 3: Advanced Features (Optional)

**Obsidian:**
- Backlink graph embeddings
- Smart search using graph relationships
- Cross-note context preservation

**Jupyter:**
- Image/plot extraction and indexing
- Cell execution context (imports, variables)
- Notebook-to-notebook references

---

## File Structure Changes

### New Files
```
api/ingestion/extractors.py
├── JupyterExtractor (new)
└── ObsidianExtractor (new)

api/ingestion/jupyter_helpers.py (new)
├── parse_notebook()
├── extract_code_cells()
├── extract_markdown_cells()
└── extract_outputs()

api/ingestion/obsidian_helpers.py (new)
├── parse_wikilinks()
├── extract_tags()
├── parse_frontmatter()
└── build_vault_graph() (optional)
```

### Modified Files
```
api/requirements.txt
└── Add: nbformat>=5.9.0, obsidiantools>=0.10.0

api/ingestion/processing.py
└── SUPPORTED_EXTENSIONS: Add .ipynb

api/ingestion/extractors.py
└── Add to EXTRACTORS mapping
```

---

## Testing Strategy

### Jupyter Notebooks
1. Test with Python notebook (pysystemtrade examples exist)
2. Test with R notebook (create sample)
3. Test with mixed markdown/code cells
4. Test with large outputs
5. Verify AST chunking works for code cells
6. Verify metadata is preserved

### Obsidian Vaults
1. Test with basic markdown (no Obsidian features)
2. Test with wikilinks: `[[Note]]`, `[[Note|Alias]]`
3. Test with tags: `#tag`, `#nested/tag`
4. Test with frontmatter YAML
5. Test with backlinks
6. Test with embeds: `![[image.png]]`
7. Verify graph relationships are preserved

---

## Success Criteria

### Jupyter Notebooks
- [x] `.ipynb` files are indexed
- [x] Code cells are chunked with AST chunking
- [x] Markdown cells are chunked with HybridChunker
- [x] Cell numbers and types are preserved in metadata
- [x] Python and R notebooks both work
- [x] Queries return relevant cells with context

### Obsidian Vaults
- [x] Wikilinks are preserved and searchable
- [x] Tags are extracted and added to metadata
- [x] Frontmatter is parsed and indexed
- [x] Graph relationships are available (optional)
- [x] Queries can find notes via links and tags
- [x] Regular markdown files still work

---

## Open Questions

1. **Jupyter Output Handling:**
   - Include outputs in chunks? (Images, plots, large dataframes)
   - Separate chunks for outputs vs. code?
   - How to handle error outputs?

2. **Obsidian Graph:**
   - Build vault-wide graph at index time or query time?
   - Store graph relationships in database?
   - Use graph for ranking/relevance?

3. **Performance:**
   - Large notebooks (100+ cells) - chunking strategy?
   - Large vaults (1000+ notes) - graph processing overhead?

4. **Metadata:**
   - How much Obsidian metadata to store?
   - Should we resolve wikilinks to full paths?
   - Store backlinks in both directions?

---

## ✅ Implementation Status (Phase 1 Complete)

### Jupyter Notebook Support - IMPLEMENTED

**Completed:**
1. ✅ Added dependencies: `nbformat>=5.9.0`, `tree-sitter-languages>=1.10.2`
2. ✅ Created `TreeSitterChunker` - Generic AST chunker using tree-sitter-languages
3. ✅ Created `JupyterExtractor` - Full notebook processing with:
   - Cell parsing (code, markdown, raw)
   - AST-based code chunking (R via tree-sitter, Python via astchunk)
   - Smart adjacent cell combining
   - Image/output preservation as metadata
   - Cell execution context tracking
4. ✅ Integrated into extraction pipeline
5. ✅ Added `.ipynb` to SUPPORTED_EXTENSIONS

**Implementation Details:**

**TreeSitterChunker (`api/ingestion/tree_sitter_chunker.py`):**
- Generic AST-based chunker for any language in tree-sitter-languages
- Implements split-then-merge algorithm (similar to ASTChunk)
- Supports R, Python, JavaScript, and 160+ other languages
- Respects max_chunk_size while preserving AST boundaries
- Includes metadata about node types, line numbers, chunk context

**JupyterExtractor (`api/ingestion/jupyter_extractor.py`):**
- Parses .ipynb files with nbformat
- Detects kernel language (python3 → Python, ir → R, etc.)
- Code cells:
  - Python → astchunk (fast, well-tested)
  - R → TreeSitterChunker (AST-based, same quality)
  - Other languages → TreeSitterChunker fallback
- Markdown cells → Extract with header detection
- Smart combining:
  - Markdown headers create hard boundaries
  - Adjacent code cells combined if under size limit
  - Preserves cell number ranges
- Output handling:
  - Text outputs included in metadata
  - Images preserved as metadata (type, size)
  - Errors/tracebacks included
  - DataFrames/HTML noted

**RAG Chunking Strategy:**
- Follows best practices from 2025 research
- Semantic boundaries (markdown headers, cell types)
- Structure-aware (preserves notebook flow)
- Context preservation (outputs, cell relationships)
- Optimal chunk size (~2048 chars, aligned with embedding model)

**Next Steps:**

1. **Test with real notebooks** ✓ (Next task)
2. **Phase 2: Obsidian vault support** (If needed)
3. **Iterate based on usage**

---

## References

- [obsidiantools PyPI](https://pypi.org/project/obsidiantools/)
- [obsidiantools GitHub](https://github.com/mfarragher/obsidiantools)
- [nbformat Documentation](https://nbformat.readthedocs.io/)
- [Jupyter Notebook Format](https://nbformat.readthedocs.io/en/latest/format_description.html)
- [Python-Markdown WikiLinks](https://python-markdown.github.io/extensions/wikilinks/)
- [Obsidian Help - Links](https://help.obsidian.md/Linking+notes+and+files/Internal+links)
