# Sandi Metz Refactoring Plan - v0.9.0-alpha
## Safe Refactoring with Test Coverage

**Date:** 2025-11-19
**Goal:** Refactor to Sandi Metz ideal while maintaining backward compatibility
**Strategy:** Test-Driven Refactoring (write tests first, then refactor)
**Companion Documents:**
- SANDI_METZ_AUDIT_v0.9.0.md (metrics)
- POODR_DESIGN_AUDIT_v0.9.0.md (design issues)

---

## Current Test Coverage Assessment

### Existing Tests
- ✅ **Obsidian Graph Cleanup**: 11 tests (comprehensive)
- ✅ **Graph Repository**: Covered via cleanup tests
- ❌ **JupyterExtractor**: **NO TESTS** (critical gap!)
- ❌ **ObsidianExtractor**: **NO TESTS** (missing!)
- ⚠️ **ObsidianGraphBuilder**: Partially covered via repository tests

### Test Coverage Gap Analysis

| Module | Current Tests | Lines | Coverage | Risk |
|--------|---------------|-------|----------|------|
| `jupyter_extractor.py` | **0** | 499 | 0% | 🔴 **CRITICAL** |
| `obsidian_extractor.py` | **0** | 321 | 0% | 🔴 **HIGH** |
| `obsidian_graph.py` | ~3 (indirect) | 367 | ~20% | 🟡 **MEDIUM** |
| `graph_repository.py` | 11 | 398 | ~60% | 🟢 **OK** |
| `obsidian_detector.py` | 0 | 98 | 0% | 🟡 **LOW** (simple) |

**Conclusion:** Must write characterization tests BEFORE refactoring!

---

## Refactoring Strategy: Test-First Approach

### Principles (from POODR + Refactoring: Improving the Design of Existing Code)

1. **"Refactoring without tests is just changing stuff"** - Martin Fowler
2. **"The tests are a canary in the coal mine"** - Sandi Metz (POODR Ch. 9)
3. **Characterization Tests**: Document current behavior before changing it
4. **Red-Green-Refactor**: Write test (red) → Make it pass (green) → Refactor (green stays green)

### Safety Net Requirements

Before refactoring ANY module:
1. ✅ **100% of public methods** must have characterization tests
2. ✅ **All integration paths** must be covered
3. ✅ **Edge cases** from audit (CC complexity hotspots)
4. ✅ **Regression tests** for known bugs

---

## Phase 0: Test Infrastructure (Prerequisite)

**Duration:** 1 day
**Branch:** `feature/sandi-metz-refactor`
**Goal:** Create safety net before ANY refactoring

### Tasks

- [x] Create git branch
- [ ] Write characterization tests for JupyterExtractor
- [ ] Write characterization tests for ObsidianExtractor
- [ ] Write characterization tests for ObsidianGraphBuilder
- [ ] Write characterization tests for GraphRepository (expand existing)
- [ ] Establish baseline test suite
- [ ] Document test coverage metrics

### Test Files to Create

```
api/tests/
├── test_jupyter_extractor.py          # NEW - Critical!
├── test_obsidian_extractor.py         # NEW - Critical!
├── test_obsidian_graph_builder.py     # NEW - Expand coverage
├── test_graph_repository.py           # NEW - Dedicated tests
└── test_obsidian_graph_cleanup.py     # EXISTS - Keep as-is
```

---

## Phase 0 Detailed: Characterization Test Specifications

### 0.1 JupyterExtractor Characterization Tests

**File:** `api/tests/test_jupyter_extractor.py`
**Coverage Target:** 80% (focus on public API)

#### Test Categories

**A. Notebook Reading & Parsing**
```python
def test_extract_simple_notebook():
    """Test: Can extract from valid .ipynb file"""
    # Given: Simple notebook with 1 code cell, 1 markdown cell
    # When: extract() called
    # Then: Returns list of chunks with correct structure

def test_extract_empty_notebook():
    """Test: Handle notebook with no cells gracefully"""

def test_extract_invalid_notebook():
    """Test: Handle corrupted .ipynb file"""

def test_parse_notebook_preserves_cell_order():
    """Test: Cells extracted in execution order"""
```

**B. Output Parsing (CC=17 - High Complexity!)**
```python
def test_parse_outputs_stream():
    """Test: Parse stdout/stderr stream outputs"""
    # From audit: _parse_outputs has CC 17 (complex branching)

def test_parse_outputs_execute_result():
    """Test: Parse execution results (text/plain)"""

def test_parse_outputs_display_data_with_image():
    """Test: Parse image outputs (PNG/JPEG)"""

def test_parse_outputs_error_traceback():
    """Test: Parse error outputs with traceback"""

def test_parse_outputs_html_dataframe():
    """Test: Parse HTML/DataFrame outputs"""

def test_parse_outputs_empty_list():
    """Test: Handle cells with no outputs"""
```

**C. Language Detection**
```python
def test_detect_language_python_kernel():
    """Test: 'python3' kernel → 'python'"""

def test_detect_language_r_kernel():
    """Test: 'ir' kernel → 'r'"""

def test_detect_language_julia_kernel():
    """Test: Julia kernel detection"""

def test_detect_language_unknown_kernel():
    """Test: Unknown kernel → fallback"""
```

**D. Code Cell Chunking (CC=12 - High Complexity!)**
```python
def test_chunk_code_cell_python_small():
    """Test: Small Python cell (<2048 chars) kept whole"""

def test_chunk_code_cell_python_large_ast():
    """Test: Large Python cell (>2048) uses ASTChunkBuilder"""
    # Mock ASTChunkBuilder to verify it's called

def test_chunk_code_cell_python_ast_failure():
    """Test: AST chunking fails → fallback to whole cell"""

def test_chunk_code_cell_r_small():
    """Test: Small R cell kept whole"""

def test_chunk_code_cell_r_large_treesitter():
    """Test: Large R cell uses TreeSitterChunker"""

def test_chunk_code_cell_r_treesitter_failure():
    """Test: TreeSitter fails → fallback"""

def test_chunk_code_cell_empty_source():
    """Test: Empty cell returns empty list"""
```

**E. Markdown Cell Chunking**
```python
def test_chunk_markdown_cell_with_headers():
    """Test: Split markdown on ## headers"""

def test_chunk_markdown_cell_no_headers():
    """Test: Small markdown kept whole"""
```

**F. Cell Combination Logic (CC=10)**
```python
def test_combine_adjacent_markdown_cells():
    """Test: Adjacent markdown cells combined"""

def test_combine_code_markdown_not_combined():
    """Test: Code + markdown NOT combined"""

def test_combine_respects_max_chunk_size():
    """Test: Doesn't combine if exceeds 2048 chars"""
```

**G. Integration Tests**
```python
def test_extract_real_notebook_python():
    """Integration: Extract from real Python notebook"""
    # Use fixture: tests/fixtures/sample_python.ipynb

def test_extract_real_notebook_r():
    """Integration: Extract from real R notebook"""
    # Use fixture: tests/fixtures/sample_r.ipynb

def test_extract_preserves_execution_count():
    """Test: Execution counts preserved in chunks"""

def test_extract_preserves_outputs():
    """Test: Cell outputs included in chunks"""
```

**Total JupyterExtractor Tests:** ~25-30 tests

---

### 0.2 ObsidianExtractor Characterization Tests

**File:** `api/tests/test_obsidian_extractor.py`
**Coverage Target:** 80%

#### Test Categories

**A. Note Extraction**
```python
def test_extract_note_basic():
    """Test: Extract simple Obsidian note"""

def test_extract_note_with_frontmatter():
    """Test: Extract and parse YAML frontmatter"""

def test_extract_note_with_wikilinks():
    """Test: Extract note with [[wikilinks]]"""

def test_extract_note_with_tags():
    """Test: Extract note with #hashtags"""
```

**B. Frontmatter Parsing**
```python
def test_extract_frontmatter_valid_yaml():
    """Test: Parse valid YAML frontmatter"""

def test_extract_frontmatter_invalid_yaml():
    """Test: Handle malformed YAML gracefully"""

def test_extract_frontmatter_missing():
    """Test: Handle notes without frontmatter"""

def test_remove_frontmatter_from_content():
    """Test: Frontmatter removed from chunk content"""
```

**C. Semantic Chunking (CC=16 - High Complexity!)**
```python
def test_chunk_semantically_by_headers():
    """Test: Split on H1, H2, H3 headers"""
    # From audit: _chunk_semantically has CC 16

def test_chunk_semantically_respects_max_size():
    """Test: Chunks don't exceed 2048 chars"""

def test_chunk_semantically_overlap():
    """Test: 200-char overlap between chunks"""

def test_chunk_semantically_no_headers():
    """Test: Single chunk if no headers"""

def test_chunk_semantically_nested_headers():
    """Test: Preserve header hierarchy (H1 → H2 → H3)"""
```

**D. Graph Metadata Building**
```python
def test_build_graph_metadata_tags():
    """Test: Extract tags from note"""

def test_build_graph_metadata_wikilinks():
    """Test: Extract wikilinks from note"""

def test_build_graph_metadata_backlinks():
    """Test: Query backlinks from graph"""

def test_build_graph_metadata_related_notes():
    """Test: Get N-hop related notes"""
```

**E. Chunk Enrichment (CC=8)**
```python
def test_enrich_chunks_with_graph_footer():
    """Test: Add graph metadata footer to chunks"""

def test_enrich_chunks_includes_tags():
    """Test: Tags included in enrichment"""

def test_enrich_chunks_includes_wikilinks():
    """Test: Wikilinks included"""

def test_enrich_chunks_includes_backlinks():
    """Test: Backlinks included"""

def test_enrich_chunks_related_notes_limit():
    """Test: Related notes truncated to N"""
```

**F. Vault-Level Extraction**
```python
def test_extract_vault_multiple_notes():
    """Test: Process all .md files in vault"""

def test_extract_vault_skip_obsidian_folder():
    """Test: Skip .obsidian/ directory"""

def test_extract_vault_skip_templates():
    """Test: Skip template files"""

def test_extract_vault_builds_graph():
    """Test: Graph built from vault structure"""

def test_extract_vault_persists_graph():
    """Test: Graph saved to database"""
```

**Total ObsidianExtractor Tests:** ~25-30 tests

---

### 0.3 ObsidianGraphBuilder Characterization Tests

**File:** `api/tests/test_obsidian_graph_builder.py`
**Coverage Target:** 70% (expand existing indirect coverage)

#### Test Categories

**A. Node Creation**
```python
def test_add_note_node():
    """Test: Add note node to graph"""

def test_add_tag_node():
    """Test: Add tag node"""

def test_add_header_node():
    """Test: Add header node with hierarchy"""

def test_add_placeholder_node():
    """Test: Add placeholder for missing wikilink"""
```

**B. Edge Creation**
```python
def test_add_wikilink_edge():
    """Test: Create wikilink edge between notes"""

def test_add_backlink_edge():
    """Test: Backlinks created automatically"""

def test_add_tag_edge():
    """Test: Note → tag edge"""

def test_add_header_hierarchy_edge():
    """Test: Header child edges (H1 → H2)"""
```

**C. Graph Queries**
```python
def test_get_connected_nodes_1_hop():
    """Test: Get immediate neighbors"""

def test_get_connected_nodes_2_hop():
    """Test: Multi-hop traversal"""

def test_get_backlinks():
    """Test: Query backlinks for note"""

def test_get_tags_for_note():
    """Test: Get all tags for note"""

def test_get_notes_with_tag():
    """Test: Reverse lookup: tag → notes"""
```

**D. Graph Analysis**
```python
def test_compute_pagerank():
    """Test: PageRank scores computed"""

def test_export_graph_format():
    """Test: Export to dict format"""

def test_import_graph_from_dict():
    """Test: Import graph from serialized format"""
```

**Total ObsidianGraphBuilder Tests:** ~15-20 tests

---

### 0.4 GraphRepository Characterization Tests

**File:** `api/tests/test_graph_repository.py`
**Coverage Target:** 80% (expand beyond cleanup tests)

#### Test Categories

**A. Node CRUD**
```python
def test_save_node():
    """Test: Insert node into database"""

def test_get_node():
    """Test: Retrieve node by ID"""

def test_delete_node():
    """Test: Delete single node"""

def test_update_node_path():
    """Test: Update note path on file move"""
```

**B. Edge CRUD**
```python
def test_save_edge():
    """Test: Insert edge"""

def test_get_edges_from():
    """Test: Query outgoing edges"""

def test_get_edges_to():
    """Test: Query incoming edges"""
```

**C. Graph Persistence (CC=8)**
```python
def test_persist_graph_nodes():
    """Test: Bulk save nodes from graph"""

def test_persist_graph_edges():
    """Test: Bulk save edges"""

def test_persist_graph_transaction():
    """Test: Atomic commit (all or nothing)"""
```

**D. Multi-Hop Queries**
```python
def test_get_connected_nodes_multi_hop_1():
    """Test: 1-hop neighbors"""

def test_get_connected_nodes_multi_hop_2():
    """Test: 2-hop traversal via SQL"""

def test_get_connected_nodes_multi_hop_empty():
    """Test: No connections returns empty"""
```

**E. Cleanup Operations** (already tested in test_obsidian_graph_cleanup.py)
```python
# Keep existing 11 tests in test_obsidian_graph_cleanup.py
# Reference them from this file
```

**Total GraphRepository Tests:** ~15 new + 11 existing = 26 tests

---

## Test Infrastructure Setup

### Fixtures Required

**api/tests/conftest.py** (expand)
```python
import pytest
import tempfile
from pathlib import Path

@pytest.fixture
def temp_notebook_path():
    """Create temporary .ipynb file"""
    with tempfile.NamedTemporaryFile(suffix='.ipynb', delete=False) as f:
        yield Path(f.name)
    Path(f.name).unlink()

@pytest.fixture
def sample_python_notebook():
    """Fixture: Simple Python notebook"""
    return {
        'cells': [
            {
                'cell_type': 'code',
                'source': 'print("hello")',
                'outputs': [],
                'execution_count': 1
            },
            {
                'cell_type': 'markdown',
                'source': '# Title\n\nDescription'
            }
        ],
        'metadata': {
            'kernelspec': {
                'name': 'python3',
                'language': 'python'
            }
        },
        'nbformat': 4,
        'nbformat_minor': 5
    }

@pytest.fixture
def sample_obsidian_note():
    """Fixture: Sample Obsidian note content"""
    return """---
tags: [test, example]
created: 2025-01-01
---

# Main Title

This is a note with [[wikilink]] and #hashtag.

## Section 1

Content here.
"""

@pytest.fixture
def temp_obsidian_vault(tmp_path):
    """Fixture: Temporary Obsidian vault"""
    vault = tmp_path / "test_vault"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    return vault
```

### Test Data Files

Create `api/tests/fixtures/`:
```
api/tests/fixtures/
├── sample_python.ipynb         # Real Python notebook
├── sample_r.ipynb              # Real R notebook
├── sample_julia.ipynb          # Real Julia notebook
├── notebook_with_errors.ipynb  # Has execution errors
├── notebook_with_images.ipynb  # Has PNG outputs
└── obsidian_vault/             # Sample vault
    ├── .obsidian/
    ├── Note1.md
    ├── Note2.md
    └── Folder/
        └── Note3.md
```

---

## Phase 1: Dependency Injection (After Tests Written)

**Duration:** 2-3 days
**Branch:** Same (`feature/sandi-metz-refactor`)
**Goal:** Inject dependencies instead of creating them

### 1.1 Extract ChunkerFactory (JupyterExtractor)

**Target:** Remove concrete dependencies on ASTChunkBuilder, TreeSitterChunker

#### Step 1: Create Abstraction
```python
# api/ingestion/chunker_factory.py (NEW FILE)

from abc import ABC, abstractmethod
from typing import List, Dict

class ChunkerInterface(ABC):
    """Abstract chunker interface (POODR: depend on abstractions)"""

    @abstractmethod
    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk source code into semantic units"""
        pass

class PythonChunker(ChunkerInterface):
    """Wraps ASTChunkBuilder"""

    def __init__(self, max_chunk_size: int = 2048):
        from astchunk import ASTChunkBuilder
        self.chunker = ASTChunkBuilder(
            max_chunk_size=max_chunk_size,
            language='python',
            metadata_template='default'
        )

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        return [
            {'content': chunk.content, 'metadata': chunk.metadata}
            for chunk in self.chunker.chunkify(source)
        ]

class RChunker(ChunkerInterface):
    """Wraps TreeSitterChunker for R"""

    def __init__(self, max_chunk_size: int = 2048):
        from ingestion.tree_sitter_chunker import TreeSitterChunker
        self.chunker = TreeSitterChunker(
            language='r',
            max_chunk_size=max_chunk_size,
            metadata_template='default'
        )

    def chunkify(self, source: str, filepath: str = '', **kwargs) -> List[Dict]:
        return self.chunker.chunkify(source, filepath=filepath)

class CellLevelChunker(ChunkerInterface):
    """Default: Keep entire cell as one chunk"""

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        return [{'content': source, 'metadata': {'chunking': 'cell_level'}}]

class ChunkerFactory:
    """Factory for creating language-specific chunkers"""

    def __init__(self, max_chunk_size: int = 2048):
        self.max_chunk_size = max_chunk_size

    def create_chunker(self, language: str, cell_size: int) -> ChunkerInterface:
        """Create appropriate chunker for language and size"""
        if language == 'python' and cell_size > self.max_chunk_size:
            return PythonChunker(self.max_chunk_size)
        elif language == 'r' and cell_size > self.max_chunk_size:
            return RChunker(self.max_chunk_size)
        else:
            return CellLevelChunker()
```

#### Step 2: Refactor JupyterExtractor (inject dependency)
```python
# api/ingestion/jupyter_extractor.py (REFACTORED)

class JupyterExtractor:
    def __init__(self, chunker_factory: ChunkerFactory = None):
        """Inject chunker factory (POODR: dependency injection)"""
        self.chunker_factory = chunker_factory or ChunkerFactory()

    def _chunk_code_cell(self, cell: NotebookCell, language: str, filepath: str) -> List[Dict]:
        """Simplified: delegate to chunker (POODR: Single Responsibility)"""
        if not cell.source or not cell.source.strip():
            return []

        cell_size = len(cell.source)
        chunker = self.chunker_factory.create_chunker(language, cell_size)

        try:
            chunks = chunker.chunkify(cell.source, filepath=filepath)
            # Add cell metadata to each chunk
            return self._enrich_chunks_with_cell_metadata(chunks, cell, language, filepath)
        except Exception as e:
            # Fallback
            return self._create_fallback_chunk(cell, language, filepath, error=str(e))
```

#### Step 3: Run Tests
```bash
# Tests should PASS (behavior unchanged)
pytest api/tests/test_jupyter_extractor.py -v
```

**Benefits:**
- ✅ Testable (inject mock chunker)
- ✅ Open/Closed (add new languages without changing JupyterExtractor)
- ✅ POODR compliant (depends on abstraction)

---

### 1.2 Inject GraphBuilder (ObsidianExtractor)

**Target:** Remove `self.graph_builder = ObsidianGraphBuilder()` from `__init__`

#### Step 1: Refactor Constructor
```python
# api/ingestion/obsidian_extractor.py (REFACTORED)

class ObsidianExtractor:
    def __init__(self, vault_path: str, graph_builder=None):
        """Inject graph_builder (POODR: dependency injection)"""
        self.vault_path = Path(vault_path)
        self.graph_builder = graph_builder  # ← Injected, not created!

    # ... rest unchanged
```

#### Step 2: Update Callers
```python
# Wherever ObsidianExtractor is used:

# Before:
extractor = ObsidianExtractor(vault_path)

# After:
graph_builder = ObsidianGraphBuilder()
extractor = ObsidianExtractor(vault_path, graph_builder=graph_builder)

# Or use default:
extractor = ObsidianExtractor(vault_path)  # graph_builder=None → lazy init
```

#### Step 3: Run Tests
```bash
pytest api/tests/test_obsidian_extractor.py -v
```

---

### 1.3 Create Abstract GraphBuilder Interface (Optional but Recommended)

```python
# api/ingestion/graph_builder_interface.py (NEW)

from abc import ABC, abstractmethod

class GraphBuilderInterface(ABC):
    """Abstract interface for graph builders (POODR: duck typing)"""

    @abstractmethod
    def add_note(self, note_id: str, title: str, content: str, filepath: str, metadata: dict):
        pass

    @abstractmethod
    def get_backlinks(self, note_id: str) -> List[str]:
        pass

    # ... other required methods

# ObsidianGraphBuilder implements this interface
class ObsidianGraphBuilder(GraphBuilderInterface):
    # ... existing implementation
```

**Benefits:**
- ✅ Can swap graph implementations
- ✅ Testable with mock graph builder
- ✅ Duck typing (POODR Chapter 5)

---

## Phase 2: Split God Classes (After Phase 1 Tests Pass)

**Duration:** 3-5 days
**Goal:** Single Responsibility Principle compliance

### 2.1 JupyterExtractor Decomposition

**Current:** 1 class, 7 responsibilities, 467 lines
**Target:** 5 focused classes, <100 lines each

#### New Class Structure

```python
# api/ingestion/jupyter/notebook_reader.py (NEW)
class NotebookReader:
    """Single Responsibility: Read .ipynb files"""

    def read(self, filepath: str) -> Notebook:
        """Read notebook from disk"""
        pass

# api/ingestion/jupyter/output_parser.py (NEW)
class NotebookOutputParser:
    """Single Responsibility: Parse cell outputs"""

    def parse_outputs(self, outputs: List) -> List[Dict]:
        """Parse notebook outputs (CC 17 → extracted!)"""
        pass

# api/ingestion/jupyter/language_detector.py (NEW)
class KernelLanguageDetector:
    """Single Responsibility: Map kernel → language"""

    def detect_language(self, kernel_name: str) -> str:
        pass

# api/ingestion/jupyter/markdown_chunker.py (NEW)
class MarkdownCellChunker:
    """Single Responsibility: Chunk markdown cells"""

    def chunk(self, cell: NotebookCell, filepath: str) -> List[Dict]:
        pass

# api/ingestion/jupyter/cell_combiner.py (NEW)
class CellCombiner:
    """Single Responsibility: Combine adjacent cells"""

    def combine_adjacent(self, chunks: List[Dict]) -> List[Dict]:
        """CC 10 logic extracted here"""
        pass

# api/ingestion/jupyter_extractor.py (REFACTORED)
class JupyterExtractor:
    """Orchestrator: Coordinates extraction pipeline"""

    def __init__(
        self,
        reader: NotebookReader = None,
        chunker_factory: ChunkerFactory = None,
        output_parser: NotebookOutputParser = None,
        language_detector: KernelLanguageDetector = None,
        markdown_chunker: MarkdownCellChunker = None,
        cell_combiner: CellCombiner = None
    ):
        """Inject all dependencies (POODR: composition over inheritance)"""
        self.reader = reader or NotebookReader()
        self.chunker_factory = chunker_factory or ChunkerFactory()
        self.output_parser = output_parser or NotebookOutputParser()
        self.language_detector = language_detector or KernelLanguageDetector()
        self.markdown_chunker = markdown_chunker or MarkdownCellChunker()
        self.cell_combiner = cell_combiner or CellCombiner()

    def extract(self, filepath: str) -> List[Dict]:
        """Orchestrate extraction (single responsibility!)"""
        notebook = self.reader.read(filepath)
        language = self.language_detector.detect_language(notebook.kernel)

        chunks = []
        for cell in notebook.cells:
            if cell.type == 'code':
                cell_chunks = self._chunk_code_cell(cell, language, filepath)
            else:
                cell_chunks = self.markdown_chunker.chunk(cell, filepath)
            chunks.extend(cell_chunks)

        return self.cell_combiner.combine_adjacent(chunks)

    def _chunk_code_cell(self, cell, language, filepath):
        """Delegate to chunker factory (already refactored in Phase 1)"""
        chunker = self.chunker_factory.create_chunker(language, len(cell.source))
        return chunker.chunkify(cell.source, filepath=filepath)
```

**Result:**
- ✅ JupyterExtractor: ~80 lines (down from 467!)
- ✅ Each class <100 lines (Sandi Metz Rule 1 compliant)
- ✅ Each class has single, clear responsibility
- ✅ All independently testable

#### Migration Strategy
1. Extract one class at a time
2. Run tests after each extraction
3. Keep old JupyterExtractor working during migration
4. Create `JupyterExtractorV2` alias
5. Switch callers one by one
6. Remove old code when all callers migrated

---

### 2.2 ObsidianExtractor Decomposition

**Current:** 1 class, 4 responsibilities, 237 lines
**Target:** 4 focused classes

```python
# api/ingestion/obsidian/frontmatter_parser.py (NEW)
class FrontmatterParser:
    """Single Responsibility: Parse YAML frontmatter"""

    def extract(self, content: str) -> Tuple[Dict, str]:
        """Returns (frontmatter_dict, content_without_frontmatter)"""
        pass

# api/ingestion/obsidian/semantic_chunker.py (NEW)
class SemanticChunker:
    """Single Responsibility: Chunk by headers"""

    def chunk(self, content: str, max_size: int = 2048, overlap: int = 200) -> List[Dict]:
        """CC 16 logic extracted here"""
        pass

# api/ingestion/obsidian/graph_enricher.py (NEW)
class GraphEnricher:
    """Single Responsibility: Enrich chunks with graph metadata"""

    def enrich(self, chunks: List[Dict], note_id: str, graph_builder) -> List[Dict]:
        """CC 8 logic extracted here"""
        pass

# api/ingestion/obsidian_extractor.py (REFACTORED)
class ObsidianExtractor:
    """Orchestrator: Coordinates Obsidian extraction"""

    def __init__(
        self,
        vault_path: str,
        graph_builder=None,
        frontmatter_parser: FrontmatterParser = None,
        semantic_chunker: SemanticChunker = None,
        graph_enricher: GraphEnricher = None
    ):
        self.vault_path = Path(vault_path)
        self.graph_builder = graph_builder
        self.frontmatter_parser = frontmatter_parser or FrontmatterParser()
        self.semantic_chunker = semantic_chunker or SemanticChunker()
        self.graph_enricher = graph_enricher or GraphEnricher()

    def extract(self, filepath: str) -> List[Dict]:
        """Orchestrate extraction (clean pipeline)"""
        content = self._read_file(filepath)
        frontmatter, clean_content = self.frontmatter_parser.extract(content)

        chunks = self.semantic_chunker.chunk(clean_content)
        note_id = self._create_note_id(filepath)

        if self.graph_builder:
            chunks = self.graph_enricher.enrich(chunks, note_id, self.graph_builder)

        return chunks
```

---

### 2.3 GraphRepository Decomposition

**Current:** 1 class, 6 responsibilities, 386 lines
**Target:** 4 focused repositories

```python
# api/ingestion/graph/node_repository.py (NEW)
class NodeRepository:
    """Single Responsibility: Node CRUD operations"""

    def save(self, node: GraphNode):
        pass

    def get(self, node_id: str) -> GraphNode:
        pass

    def delete(self, node_id: str):
        pass

# api/ingestion/graph/edge_repository.py (NEW)
class EdgeRepository:
    """Single Responsibility: Edge CRUD operations"""
    pass

# api/ingestion/graph/graph_metadata_repository.py (NEW)
class GraphMetadataRepository:
    """Single Responsibility: PageRank, stats"""
    pass

# api/ingestion/graph/graph_cleanup_service.py (NEW)
class GraphCleanupService:
    """Single Responsibility: Orphan cleanup, deletion logic"""

    def cleanup_orphan_tags(self):
        """Extracted from GraphRepository"""
        pass

    def cleanup_orphan_placeholders(self):
        pass

# api/ingestion/graph_repository.py (REFACTORED - Facade)
class GraphRepository:
    """Facade: Coordinates graph persistence (composition!)"""

    def __init__(self, db_conn):
        self.nodes = NodeRepository(db_conn)
        self.edges = EdgeRepository(db_conn)
        self.metadata = GraphMetadataRepository(db_conn)
        self.cleanup = GraphCleanupService(db_conn)

    # Public interface delegates to specialized repos
    def save_node(self, node):
        return self.nodes.save(node)

    def cleanup_orphan_tags(self):
        return self.cleanup.cleanup_orphan_tags()
```

**Pattern:** Facade + Composition (POODR Chapter 8)

---

## Phase 3: Duck Typing & Polymorphism (After Phase 2 Tests Pass)

**Duration:** 2-3 days
**Goal:** Eliminate conditionals via polymorphism

### 3.1 Chunkable Duck Type

**Replace:** `if cell.type == 'code': ... elif cell.type == 'markdown': ...`

```python
# api/ingestion/jupyter/chunkable.py (NEW)

class Chunkable(ABC):
    """Duck type: Objects that know how to chunk themselves"""

    @abstractmethod
    def chunk(self) -> List[Dict]:
        """Self-chunking (POODR: objects collaborate via messages)"""
        pass

class CodeCell(Chunkable):
    def __init__(self, source: str, language: str, chunker_factory):
        self.source = source
        self.language = language
        self.chunker_factory = chunker_factory

    def chunk(self) -> List[Dict]:
        """Code cell knows how to chunk itself"""
        chunker = self.chunker_factory.create_chunker(self.language, len(self.source))
        return chunker.chunkify(self.source)

class MarkdownCell(Chunkable):
    def __init__(self, source: str, markdown_chunker):
        self.source = source
        self.markdown_chunker = markdown_chunker

    def chunk(self) -> List[Dict]:
        """Markdown cell knows how to chunk itself"""
        return self.markdown_chunker.chunk(self.source)

# Usage (polymorphic - no conditionals!)
def extract(self, notebook):
    chunks = []
    for cell in notebook.cells:
        chunks.extend(cell.chunk())  # ← Duck typing magic!
    return chunks
```

**Benefits:**
- ✅ No if/elif conditionals
- ✅ Open/Closed (add new cell types without changing extractor)
- ✅ Polymorphic behavior (POODR Chapter 5)

---

### 3.2 Persistable Duck Type

```python
# api/ingestion/graph/persistable.py (NEW)

class Persistable(ABC):
    """Duck type: Objects that can persist themselves"""

    @abstractmethod
    def to_persistence_dict(self) -> Dict:
        pass

class GraphNode(Persistable):
    def __init__(self, node_id, node_type, title, content, metadata):
        self.node_id = node_id
        self.node_type = node_type
        self.title = title
        self.content = content
        self.metadata = metadata

    def to_persistence_dict(self) -> Dict:
        return {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'title': self.title,
            'content': self.content,
            'metadata': self.metadata
        }

class GraphEdge(Persistable):
    # Similar pattern

# Usage
class NodeRepository:
    def save(self, persistable: Persistable):
        """Duck typing: accepts any persistable object"""
        data = persistable.to_persistence_dict()
        self.db.execute("INSERT INTO nodes ...", data)
```

---

## Phase 4: Final Cleanup & Optimization

**Duration:** 1-2 days
**Goal:** Polish, document, optimize

### Tasks

- [ ] Remove all TODO comments
- [ ] Add docstrings to all public methods
- [ ] Create interface documentation
- [ ] Run static analysis (mypy, pylint)
- [ ] Optimize hot paths (if needed)
- [ ] Update README with new architecture

---

## Testing Strategy Throughout Refactoring

### Golden Rule: Tests Must Always Pass ✅

After EVERY step:
```bash
# Run specific module tests
pytest api/tests/test_jupyter_extractor.py -v

# Run full suite
pytest api/tests/ -v

# Check coverage
pytest api/tests/ --cov=api/ingestion --cov-report=term-missing
```

### When Tests Fail

1. **Stop immediately** - Don't continue refactoring
2. **Identify root cause** - New bug or test needs updating?
3. **Fix the issue** - Update code or test (not both arbitrarily)
4. **Verify green** - All tests pass before continuing

### Test Coverage Goals

| Phase | Coverage Target |
|-------|-----------------|
| Phase 0 (Baseline) | 70% overall |
| Phase 1 (Injection) | 75% overall |
| Phase 2 (Decomposition) | 80% overall |
| Phase 3 (Duck Types) | 85% overall |
| Phase 4 (Final) | 90% overall |

---

## Git Workflow

### Branch Strategy

```bash
# Create feature branch
git checkout -b feature/sandi-metz-refactor

# Work in small commits
git commit -m "test: Add JupyterExtractor characterization tests"
git commit -m "refactor: Extract ChunkerFactory from JupyterExtractor"
git commit -m "test: Verify ChunkerFactory injection works"

# Push frequently
git push origin feature/sandi-metz-refactor

# Create PR when ready
gh pr create --title "Refactor to Sandi Metz ideal (POODR)" --body "..."
```

### Commit Message Convention

```
<type>: <description>

Types:
- test: Add/modify tests
- refactor: Change code structure (no behavior change)
- fix: Bug fix
- docs: Documentation
```

### Checkpoints (Create Tags)

```bash
# After Phase 0 (tests written)
git tag -a phase0-tests-complete -m "All characterization tests written"

# After Phase 1 (dependency injection)
git tag -a phase1-injection-complete -m "Dependencies injected"

# After Phase 2 (decomposition)
git tag -a phase2-decomposition-complete -m "God classes split"

# After Phase 3 (duck typing)
git tag -a phase3-duck-types-complete -m "Polymorphism introduced"

# Final
git tag -a v0.10.0-alpha -m "Sandi Metz refactor complete"
```

---

## Rollback Plan

If refactoring introduces regressions:

### Option 1: Fix Forward
```bash
# Fix the issue in current branch
# Add test for regression
# Commit fix
```

### Option 2: Revert to Checkpoint
```bash
# Go back to last good tag
git reset --hard phase1-injection-complete

# Create new branch from there
git checkout -b feature/sandi-metz-refactor-v2
```

### Option 3: Emergency Rollback
```bash
# Abandon refactor, return to main
git checkout main

# Refactoring branch preserved for later analysis
```

---

## Success Criteria

### Code Quality Metrics

| Metric | Before | Target | How to Measure |
|--------|--------|--------|----------------|
| Sandi Metz Violations | 74 | <10 | Custom script |
| Avg Cyclomatic Complexity | 3.23 | <3.0 | `radon cc` |
| Maintainability Index | 55.25 | >65 | `radon mi` |
| Test Coverage | ~30% | >85% | `pytest --cov` |
| Classes >100 lines | 4 | 0 | Manual count |
| Methods >5 lines | 62 | <10 | Manual count |

### POODR Compliance

| Principle | Before | After |
|-----------|--------|-------|
| Law of Demeter | ✅ A | ✅ A |
| Dependency Injection | ❌ F | ✅ A |
| Single Responsibility | ❌ D | ✅ A |
| Duck Typing | ❌ F | ✅ A |
| TRUE Code | C+ | A |

### Functional Requirements

- ✅ All existing functionality preserved
- ✅ Backward compatible API (or explicit migration guide)
- ✅ No performance regressions
- ✅ All tests passing
- ✅ No new bugs introduced

---

## Timeline Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 0: Tests** | 1 day | 70+ characterization tests |
| **Phase 1: Injection** | 2-3 days | Dependencies injected |
| **Phase 2: Decomposition** | 3-5 days | God classes split |
| **Phase 3: Duck Types** | 2-3 days | Polymorphism added |
| **Phase 4: Cleanup** | 1-2 days | Documentation, polish |
| **Testing & Fixes** | 2-3 days | All tests green |
| **TOTAL** | **11-17 days** | Sandi Metz ideal achieved |

**Realistic:** 3 weeks (15 working days) with buffer

---

## Resources & References

### From Knowledge Base (RAG)
- ✅ **POODR** (Practical Object-Oriented Design in Ruby) - Sandi Metz
- ✅ **99 Bottles of Beer** - Sandi Metz (refactoring patterns)
- ⚠️ **Refactoring** - Martin Fowler (recommended reading during refactor)
- ⚠️ **TDD by Example** - Kent Beck (test-first approach)

### External Tools
- `radon` - Complexity metrics
- `pytest` - Testing framework
- `pytest-cov` - Coverage reporting
- `mypy` - Static type checking

---

## Next Steps

### Immediate Actions (Today)

1. **Create branch**
   ```bash
   git checkout -b feature/sandi-metz-refactor
   git push -u origin feature/sandi-metz-refactor
   ```

2. **Create test fixture directories**
   ```bash
   mkdir -p api/tests/fixtures/obsidian_vault
   touch api/tests/fixtures/sample_python.ipynb
   ```

3. **Start writing characterization tests**
   - Begin with `test_jupyter_extractor.py` (highest risk - no tests currently)
   - Use TDD: Red (write test) → Green (make it pass) → Refactor

### Questions to Resolve

- [ ] Do we need feature flags for gradual rollout?
- [ ] Should we maintain v1 API alongside v2 during migration?
- [ ] What's the deprecation timeline for old interfaces?
- [ ] Do integration tests exist for end-to-end flows?

---

**Let's ship it! 🚀**

*"Make it work, make it right, make it fast" - Kent Beck*
*"Design is about managing dependencies" - Sandi Metz*

---

*Refactoring Plan created: 2025-11-19*
*Ready to execute Phase 0: Test Infrastructure*
