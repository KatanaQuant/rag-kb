# Continue Sandi Metz Refactoring - Quick Start Guide

**Current Branch:** `feature/sandi-metz-refactor`
**Latest Commit:** `553928f` - Phase 1 Complete
**Progress:** 15% (2 of 4 phases done)

---

## ✅ What's Done

### Phase 0: Test Infrastructure (100%)
- 75+ characterization tests
- Test fixtures created
- Audits completed
- **Commit:** `d612200`

### Phase 1: Dependency Injection (100%)
- ChunkerFactory extracted
- Dependencies injected
- **Metrics:** CC 12→4, MI +4.1%, LOC -10%
- **Commit:** `553928f`

---

## 🎯 Next: Phase 2 - Split God Classes

**Goal:** Break 4 God Classes (>100 lines) into focused classes

### Priority Order

1. **JupyterExtractor** (447 lines → 5 classes)
2. **ObsidianExtractor** (332 lines → 4 classes)
3. **GraphRepository** (386 lines → 4 classes)
4. **ObsidianGraphBuilder** (320 lines → 3 classes)

---

## Phase 2.1: Split JupyterExtractor

**Current:** 1 class, 447 lines, 7 responsibilities

**Target:** 5 focused classes

### Step 1: Extract NotebookOutputParser

**File:** `api/ingestion/jupyter/output_parser.py`

**Extract method:** `_parse_outputs` (CC 17 - highest complexity!)

```python
class NotebookOutputParser:
    """Single Responsibility: Parse notebook cell outputs

    Extracts CC 17 method from JupyterExtractor
    """

    @staticmethod
    def parse_outputs(outputs: List) -> List[Dict]:
        """Parse cell outputs (stream, execute_result, error, etc.)

        This is the EXACT code from JupyterExtractor._parse_outputs
        """
        # Copy lines 123-177 from jupyter_extractor.py
        pass
```

**Update JupyterExtractor:**
```python
from ingestion.jupyter.output_parser import NotebookOutputParser

# In _parse_notebook:
outputs = NotebookOutputParser.parse_outputs(cell.outputs)
```

### Step 2: Extract KernelLanguageDetector

**File:** `api/ingestion/jupyter/language_detector.py`

```python
class KernelLanguageDetector:
    """Single Responsibility: Map kernel names to languages"""

    @staticmethod
    def detect_language(kernel_name: str) -> str:
        """Detect language from kernel name

        Copy from JupyterExtractor._detect_language_from_kernel
        """
        pass
```

### Step 3: Extract MarkdownCellChunker

**File:** `api/ingestion/jupyter/markdown_chunker.py`

```python
class MarkdownCellChunker:
    """Single Responsibility: Chunk markdown cells"""

    def chunk(self, cell: NotebookCell, filepath: str) -> List[Dict]:
        """Copy from JupyterExtractor._chunk_markdown_cell"""
        pass
```

### Step 4: Extract CellCombiner

**File:** `api/ingestion/jupyter/cell_combiner.py`

```python
class CellCombiner:
    """Single Responsibility: Combine adjacent cells"""

    def combine_adjacent(self, chunks: List[Dict], filepath: str, max_chunk_size: int = 2048) -> List[Dict]:
        """Copy from JupyterExtractor._combine_adjacent_cells"""
        pass
```

### Step 5: Refactor JupyterExtractor (Orchestrator)

**New structure (~80-100 lines):**
```python
class JupyterExtractor:
    """Orchestrator: Coordinates notebook extraction pipeline

    POODR: Composition over inheritance
    Single Responsibility: Coordinate, don't do everything
    """

    def __init__(
        self,
        chunker_factory=None,
        output_parser=None,
        language_detector=None,
        markdown_chunker=None,
        cell_combiner=None
    ):
        """Inject all dependencies"""
        from ingestion.chunker_factory import ChunkerFactory
        from ingestion.jupyter.output_parser import NotebookOutputParser
        from ingestion.jupyter.language_detector import KernelLanguageDetector
        from ingestion.jupyter.markdown_chunker import MarkdownCellChunker
        from ingestion.jupyter.cell_combiner import CellCombiner

        self.chunker_factory = chunker_factory or ChunkerFactory()
        self.output_parser = output_parser or NotebookOutputParser()
        self.language_detector = language_detector or KernelLanguageDetector()
        self.markdown_chunker = markdown_chunker or MarkdownCellChunker()
        self.cell_combiner = cell_combiner or CellCombiner()

    def extract(self, path: Path) -> ExtractionResult:
        """Coordinate extraction pipeline"""
        # Parse notebook
        nb_metadata, cells = self._parse_notebook(path)
        language = self.language_detector.detect_language(nb_metadata['kernel'])

        # Process cells
        chunks = []
        for cell in cells:
            if cell.cell_type == 'code':
                cell_chunks = self._chunk_code_cell(cell, language, str(path))
            else:
                cell_chunks = self.markdown_chunker.chunk(cell, str(path))
            chunks.extend(cell_chunks)

        # Combine adjacent cells
        combined = self.cell_combiner.combine_adjacent(chunks, str(path))

        return ExtractionResult(pages=[{'content': c['content'], 'metadata': c} for c in combined])
```

---

## Commands to Execute Phase 2.1

```bash
# Create directory structure
mkdir -p api/ingestion/jupyter
touch api/ingestion/jupyter/__init__.py

# Create new files (copy code from jupyter_extractor.py)
# 1. Extract output parser
vi api/ingestion/jupyter/output_parser.py
# Copy _parse_outputs method (lines 123-177)

# 2. Extract language detector
vi api/ingestion/jupyter/language_detector.py
# Copy _detect_language_from_kernel method (lines 180-202)

# 3. Extract markdown chunker
vi api/ingestion/jupyter/markdown_chunker.py
# Copy _chunk_markdown_cell method (lines 254-284)

# 4. Extract cell combiner
vi api/ingestion/jupyter/cell_combiner.py
# Copy _combine_adjacent_cells method (lines 285-343)

# 5. Refactor JupyterExtractor to use new classes
vi api/ingestion/jupyter_extractor.py
# Update __init__ to inject dependencies
# Update extract method to use injected classes
# Remove extracted methods

# Run tests after EACH extraction
pytest api/tests/test_jupyter_extractor.py -v

# Measure metrics after each step
radon cc api/ingestion/jupyter_extractor.py -s
radon mi api/ingestion/jupyter_extractor.py -s
wc -l api/ingestion/jupyter_extractor.py

# Commit after each successful extraction
git add api/ingestion/jupyter/
git commit -m "refactor(Phase 2): Extract NotebookOutputParser from JupyterExtractor

- Extracted _parse_outputs (CC 17) into dedicated class
- Reduces JupyterExtractor complexity
- Single Responsibility: OutputParser only parses outputs

Metrics: [insert metrics]
Tests: All passing"
```

---

## Expected Metrics After Phase 2.1

| Metric | Before | Target | Change |
|--------|--------|--------|--------|
| JupyterExtractor LOC | 447 | ~150 | -66% |
| Classes >100 lines | 4 | 3 | -25% |
| Highest CC method | CC 17 | CC 8 | -53% |
| Methods >5 lines | 58 | ~40 | -31% |

---

## Phase 2.2: Split ObsidianExtractor

**Similar process:**
1. Extract `FrontmatterParser`
2. Extract `SemanticChunker` (CC 16)
3. Extract `GraphEnricher` (CC 8)
4. Refactor to orchestrator pattern

---

## Phase 2.3: Split GraphRepository

1. Extract `NodeRepository`
2. Extract `EdgeRepository`
3. Extract `GraphMetadataRepository`
4. Extract `GraphCleanupService`
5. Keep `GraphRepository` as facade

---

## Testing Strategy

**After EACH extraction:**
```bash
# Run specific tests
pytest api/tests/test_jupyter_extractor.py -v

# Run all tests
pytest api/tests/ -v

# Check for regressions
git diff HEAD~1 --stat
```

**Golden Rule:** Green → Green
- Tests must pass before AND after each refactoring
- If tests fail, fix or revert immediately

---

## Rollback if Needed

```bash
# Undo last commit
git reset --hard HEAD~1

# Or create new branch from last good commit
git checkout -b feature/sandi-metz-refactor-v2 553928f
```

---

## Final Phase Preview

### Phase 3: Duck Typing (After Phase 2)

**Chunkable Duck Type:**
```python
class Chunkable(ABC):
    @abstractmethod
    def chunk(self) -> List[Dict]:
        pass

class CodeCell(Chunkable):
    def chunk(self):
        # Knows how to chunk itself
        pass

class MarkdownCell(Chunkable):
    def chunk(self):
        # Knows how to chunk itself
        pass

# Usage (polymorphic - no conditionals!)
for cell in notebook.cells:
    chunks.extend(cell.chunk())  # Duck typing magic!
```

### Phase 4: Final Polish

- Add docstrings
- Run full test suite
- Fix any remaining issues
- Update README
- Squash commits
- Merge to main

---

## Progress Tracking

| Phase | Status | Commits |
|-------|--------|---------|
| Phase 0: Tests | ✅ Done | `d612200` |
| Phase 1: DI | ✅ Done | `553928f` |
| **Phase 2: Split** | ⏸️ **Next** | - |
| Phase 3: Duck Types | ⏸️ Pending | - |
| Phase 4: Polish | ⏸️ Pending | - |

**Overall:** 15% → 50% (after Phase 2)

---

## Key Reminders

1. **Test after EVERY change**
2. **Commit frequently** (small, atomic commits)
3. **Measure metrics** before/after
4. **Keep tests green** (no regressions)
5. **Reference POODR principles** in commits

---

## Resources

- **POODR Audit:** `docs/POODR_DESIGN_AUDIT_v0.9.0.md`
- **Refactoring Plan:** `docs/REFACTORING_PLAN_v0.9.0.md`
- **Phase 1 Metrics:** `docs/PHASE1_METRICS.md`
- **Checkpoint:** `docs/REFACTORING_CHECKPOINT_1.md`

---

**Ready to continue!** Start with Phase 2.1 Step 1 (Extract OutputParser)

*"Make it work, make it right, make it fast" - Kent Beck*
*"Design is about managing dependencies" - Sandi Metz*
