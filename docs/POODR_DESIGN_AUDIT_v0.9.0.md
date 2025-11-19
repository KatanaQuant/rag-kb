# POODR Design Audit - v0.9.0-alpha
## Practical Object-Oriented Design Analysis

**Date:** 2025-11-19
**Release:** v0.9.0-alpha (Jupyter + Obsidian Graph-RAG)
**Framework:** Sandi Metz's POODR principles
**Companion to:** SANDI_METZ_AUDIT_v0.9.0.md

---

## Executive Summary

This audit applies **POODR (Practical Object-Oriented Design in Ruby)** principles from your knowledge base to evaluate the design quality of v0.9.0 modules. While the previous audit focused on metrics (CC, MI, SLOC), this analysis examines **dependencies, coupling, interfaces, and message-passing patterns**.

### POODR Assessment

| Principle | Grade | Status |
|-----------|-------|---------|
| **Managing Dependencies** | C+ | 4 concrete dependencies, moderate coupling |
| **Single Responsibility** | B | Classes have too many responsibilities |
| **Duck Typing** | B- | Missing polymorphic interfaces |
| **Law of Demeter** | A | ✓ No message chain violations |
| **TRUE Code** | B | Reasonable but not fully transparent/usable |
| **Dependency Direction** | B+ | Generally depends on abstractions |

**Overall Design Grade:** B- (Functional but tight coupling limits flexibility)

---

## 1. Managing Dependencies (POODR Chapter 3)

### Core Principle
> "Design is about dependencies. An object depends on another object if, when one object changes, the other might be forced to change in turn."

### Current State: Moderate Coupling

**Concrete Dependencies Found:** 4 violations

| File | Line | Violation | Impact |
|------|------|-----------|--------|
| `jupyter_extractor.py` | 211 | `ASTChunkBuilder()` | Tight coupling to astchunk library |
| `jupyter_extractor.py` | 253 | `TreeSitterChunker()` | Tight coupling to tree-sitter implementation |
| `obsidian_extractor.py` | 47 | `ObsidianGraphBuilder()` | Direct instantiation in `__init__` |
| `obsidian_extractor.py` | 283 | `ObsidianGraphBuilder()` | Direct instantiation in vault extractor |

### Analysis

**jupyter_extractor.py (Lines 208-289):**
```python
# Current: Depends on concrete classes
if language == 'python' and cell_size > 2048:
    from astchunk import ASTChunkBuilder
    chunker = ASTChunkBuilder(...)  # ← Concrete dependency

elif language == 'r' and cell_size > 2048:
    from ingestion.tree_sitter_chunker import TreeSitterChunker
    chunker = TreeSitterChunker(...)  # ← Concrete dependency
```

**POODR Violation:** Feature Envy + Dependency on Concretions
- `JupyterExtractor` knows too much about how to create chunkers
- Changes to chunker APIs force changes to `JupyterExtractor`
- Cannot substitute alternative chunking strategies without modification

**Recommended Fix: Dependency Injection**
```python
class JupyterExtractor:
    def __init__(self, chunker_factory=None):
        """Inject chunker factory to remove concrete dependencies"""
        self.chunker_factory = chunker_factory or DefaultChunkerFactory()

    def _chunk_code_cell(self, cell, language, filepath):
        # Depend on abstraction, not concretion
        chunker = self.chunker_factory.create_chunker(language, cell_size)
        return chunker.chunkify(cell.source)

# Usage
extractor = JupyterExtractor(
    chunker_factory=LanguageChunkerFactory()
)
```

**Benefits:**
- Testable (inject mock chunker)
- Flexible (swap chunking strategies)
- Open/Closed (extend with new languages without modifying JupyterExtractor)

---

**obsidian_extractor.py (Line 47):**
```python
class ObsidianExtractor:
    def __init__(self, vault_path: str):
        self.graph_builder = ObsidianGraphBuilder()  # ← Concrete dependency
```

**POODR Violation:** Creates its own dependency
- `ObsidianExtractor` cannot be tested without real `ObsidianGraphBuilder`
- Cannot reuse extractor with different graph implementations
- Violates Dependency Inversion Principle (depend on abstractions)

**Recommended Fix:**
```python
class ObsidianExtractor:
    def __init__(self, vault_path: str, graph_builder=None):
        """Inject graph_builder dependency"""
        self.graph_builder = graph_builder or ObsidianGraphBuilder()
        self.vault_path = vault_path
```

---

### Law of Demeter Compliance ✓

**Finding:** No significant violations detected

From POODR:
> "Demeter restricts the set of objects to which a method may send messages. Its purpose is to reduce coupling between objects."

Your code avoids message chains like `customer.bicycle.wheel.tire`. This is excellent design discipline!

**Example of good Demeter compliance:**
```python
# obsidian_graph.py - Clean message passing
def get_backlinks(self, note_id: str) -> List[str]:
    return [edge['source'] for edge in self.get_edges_to(note_id)]
    # ✓ Sends messages only to self
```

---

## 2. Single Responsibility Principle (POODR Chapter 2)

### Core Principle
> "A class should do the smallest possible useful thing. Classes that do one thing isolate that thing from the rest of your application."

### Violations: 4 God Classes

| Class | Lines | Responsibilities | SRP Grade |
|-------|-------|------------------|-----------|
| `JupyterExtractor` | 467 | 7+ responsibilities | D |
| `ObsidianGraphBuilder` | 320 | 5+ responsibilities | C |
| `GraphRepository` | 386 | 6+ responsibilities | D |
| `ObsidianExtractor` | 237 | 4 responsibilities | C+ |

### Detailed Analysis: JupyterExtractor

**Current Responsibilities:**
1. Notebook file I/O (reading .ipynb files)
2. Output parsing (stream, execute_result, error formats)
3. Language detection (kernel → language mapping)
4. Code cell chunking (Python, R, fallback strategies)
5. Markdown cell chunking
6. Cell adjacency logic (combining related cells)
7. Chunk merging and finalization

**POODR Test: "Interrogate the class as if it's sentient"**
- "Mr. JupyterExtractor, what is your notebook?" ✓ Makes sense
- "Mr. JupyterExtractor, what are your parsed outputs?" ⚠️ Questionable
- "Mr. JupyterExtractor, what language does this kernel use?" ❌ Wrong responsibility
- "Mr. JupyterExtractor, how do you chunk R code?" ❌ Feature envy

**One-Sentence Description Test:**
> "JupyterExtractor reads notebooks AND parses outputs AND detects languages AND chunks code cells AND chunks markdown AND combines cells AND merges chunks."

**Result:** 7 "AND"s = 7 responsibilities (failed!)

### Recommended Decomposition

```python
# 1. Notebook Reader (File I/O)
class NotebookReader:
    def read(self, filepath: str) -> Notebook:
        """Single responsibility: Read .ipynb files"""

# 2. Output Parser (Data transformation)
class NotebookOutputParser:
    def parse_outputs(self, outputs: List) -> List[Dict]:
        """Single responsibility: Parse cell outputs"""

# 3. Language Detector (Configuration)
class KernelLanguageDetector:
    def detect_language(self, kernel_name: str) -> str:
        """Single responsibility: Map kernel → language"""

# 4. Cell Chunker (Strategy pattern)
class CellChunker(ABC):
    @abstractmethod
    def chunk(self, cell: NotebookCell) -> List[Dict]:
        pass

class PythonCellChunker(CellChunker):
    """Uses ASTChunkBuilder for Python"""

class RCellChunker(CellChunker):
    """Uses TreeSitterChunker for R"""

class MarkdownCellChunker(CellChunker):
    """Header-aware markdown chunking"""

# 5. Orchestrator (Composition)
class JupyterExtractor:
    def __init__(self, reader, chunker_factory):
        self.reader = reader
        self.chunker_factory = chunker_factory

    def extract(self, filepath: str) -> List[Dict]:
        """Single responsibility: Coordinate extraction pipeline"""
        notebook = self.reader.read(filepath)
        return self._process_cells(notebook)
```

**Benefits of Decomposition:**
- Each class has single, clear responsibility
- Testable in isolation (mock dependencies)
- Reusable components (use `NotebookReader` elsewhere)
- Open/Closed (add new chunkers without changing extractor)

---

## 3. Creating Flexible Interfaces (POODR Chapter 4)

### Core Principle
> "Think about interfaces. Create them intentionally. It is your interfaces, more than all of your tests and any of your code, that define your application and determine its future."

### Current Interface Issues

#### 3.1 Public vs Private Confusion

**graph_repository.py:**
```python
class GraphRepository:
    def _delete_note_and_headers(self, note_id: str):  # Private (underscore)
        """Called from public delete_note_nodes method"""

    def cleanup_orphan_tags(self):  # Public (no underscore)
        """But should this be public? Or internal cleanup?"""
```

**Issue:** Unclear interface boundaries
- What is the public contract?
- What methods should callers use?
- What methods are implementation details?

**POODR Guidance:**
> "Public methods comprise the class's public interface. They reveal its primary responsibility, are expected to be invoked by others, will not change on a whim, and are safe for others to depend on."

**Recommended Fix:**
```python
class GraphRepository:
    # PUBLIC INTERFACE (documented contract)
    def save_node(self, node: GraphNode) -> None:
        """Public: Save a graph node"""

    def delete_note(self, note_id: str) -> None:
        """Public: Delete note and cleanup orphans"""
        self._delete_note_and_headers(note_id)
        self._cleanup_orphan_tags()
        self._cleanup_orphan_placeholders()

    # PRIVATE INTERFACE (implementation details)
    def _delete_note_and_headers(self, note_id: str) -> None:
        """Private: Internal deletion logic"""

    def _cleanup_orphan_tags(self) -> None:
        """Private: Internal cleanup (not for external use)"""
```

---

#### 3.2 Ask, Don't Tell Violations

**obsidian_extractor.py (Lines 224-260):**
```python
def _enrich_chunks_with_graph(self, chunks, note_id, graph_metadata, ...):
    for chunk in chunks:
        # Telling chunk what to do instead of asking
        chunk['metadata']['tags'] = graph_metadata.get('tags', [])
        chunk['metadata']['wikilinks'] = graph_metadata.get('wikilinks', [])
        chunk['metadata']['backlinks'] = graph_metadata.get('backlinks', [])
        # ... more telling
```

**POODR Violation:** "Tell, Don't Ask" (should be reversed!)
- Method reaches into chunk dict and modifies it
- Knows too much about chunk internal structure
- Brittle to changes in chunk format

**Recommended Fix: Ask for What You Want**
```python
class EnrichedChunk:
    def enrich_with_graph(self, graph_metadata: GraphMetadata):
        """Chunk knows how to enrich itself"""
        self.add_tags(graph_metadata.tags)
        self.add_links(graph_metadata.wikilinks)
        self.add_backlinks(graph_metadata.backlinks)

# Usage (ask, don't tell)
for chunk in chunks:
    chunk.enrich_with_graph(graph_metadata)  # Chunk handles its own enrichment
```

---

## 4. Duck Typing Opportunities (POODR Chapter 5)

### Core Principle
> "Duck types are public interfaces that are not tied to any specific class. If an object quacks like a duck and walks like a duck, then its class is immaterial, it's a duck."

### Missing Duck Types

#### 4.1 Chunkable Duck Type

**Current:** Conditional logic based on cell type
```python
# jupyter_extractor.py
if cell.cell_type == 'code':
    chunks = self._chunk_code_cell(cell, ...)
elif cell.cell_type == 'markdown':
    chunks = self._chunk_markdown_cell(cell, ...)
```

**Opportunity:** Create "Chunkable" duck type
```python
# Define the duck interface
class Chunkable:
    """Duck type: Any object that can be chunked"""
    def chunk(self) -> List[Dict]:
        """All chunkables must implement this"""
        raise NotImplementedError

class CodeCell(Chunkable):
    def chunk(self) -> List[Dict]:
        """Code cell knows how to chunk itself"""
        return self.chunker.chunkify(self.source)

class MarkdownCell(Chunkable):
    def chunk(self) -> List[Dict]:
        """Markdown cell knows how to chunk itself"""
        return self._chunk_by_headers()

# Polymorphic usage (no conditionals!)
for cell in notebook.cells:
    chunks.extend(cell.chunk())  # Duck typing magic!
```

**Benefits:**
- Eliminate conditionals
- Open/Closed (add new cell types without changing extractor)
- Polymorphic behavior (objects collaborate via shared interface)

---

#### 4.2 Persistable Duck Type

**Current:** Repository knows how to persist everything
```python
class GraphRepository:
    def save_node(self, node_id, node_type, title, content, metadata):
        """Repository knows node structure"""

    def save_edge(self, source_id, target_id, edge_type, metadata):
        """Repository knows edge structure"""
```

**Opportunity:** Objects that know how to persist themselves
```python
class Persistable:
    """Duck type: Objects that can save themselves"""
    def to_persistence_dict(self) -> Dict:
        raise NotImplementedError

class GraphNode(Persistable):
    def to_persistence_dict(self) -> Dict:
        return {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'title': self.title,
            'content': self.content,
            'metadata': self.metadata
        }

class GraphRepository:
    def save(self, persistable: Persistable):
        """Duck typing: accepts any persistable object"""
        data = persistable.to_persistence_dict()
        self.db.execute("INSERT INTO ...", data)
```

---

## 5. TRUE Code Assessment (POODR Chapter 2)

### TRUE Criteria

From POODR:
> "Code should be **T**ransparent, **R**easonable, **U**sable, and **E**xemplary"

| Module | Transparent | Reasonable | Usable | Exemplary | Grade |
|--------|-------------|------------|--------|-----------|-------|
| `jupyter_extractor.py` | ⚠️ | ✓ | ❌ | ⚠️ | C+ |
| `obsidian_extractor.py` | ✓ | ✓ | ⚠️ | ✓ | B+ |
| `obsidian_graph.py` | ✓ | ✓ | ✓ | ✓ | A- |
| `obsidian_detector.py` | ✓ | ✓ | ✓ | ✓ | A |
| `graph_repository.py` | ⚠️ | ✓ | ⚠️ | ⚠️ | B- |

### Detailed Assessment

#### Transparent (consequences of change are obvious)
**jupyter_extractor.py:** ❌ Not Transparent
- Changing `ASTChunkBuilder` API breaks `_chunk_code_cell` (line 211)
- Changing cell output format breaks `_parse_outputs` (line 103)
- Dependencies are distant and hidden in try/except blocks

**obsidian_graph.py:** ✓ Transparent
- Clean method boundaries
- Clear data flow
- Changes have obvious, local effects

---

#### Reasonable (cost of change proportional to benefit)
**All modules:** ✓ Mostly Reasonable
- Changes are localized to specific methods
- No major architectural impediments

---

#### Usable (reusable in new contexts)
**jupyter_extractor.py:** ❌ Not Usable
- Cannot reuse `_chunk_code_cell` without entire JupyterExtractor class
- Tightly coupled to nbformat library
- Requires specific context (NotebookCell objects)

**obsidian_graph.py:** ✓ Highly Usable
- `ObsidianGraphBuilder` can be used standalone
- Clean interfaces for graph operations
- Minimal context requirements

---

#### Exemplary (encourages good practices)
**obsidian_detector.py:** ✓ Exemplary (reference implementation!)
- Simple, focused methods
- Clear naming
- Well-structured conditionals
- Should be used as template for other modules

**jupyter_extractor.py:** ⚠️ Not Exemplary
- Long methods encourage more long methods
- Complex conditionals breed more conditionals
- Pattern should not be replicated

---

## 6. Dependency Direction (POODR Chapter 3.4)

### Core Principle
> "Depend on things that change less often than you do."

### Dependency Stability Hierarchy

```
Most Stable (Abstract)
    ↑
    |  Interfaces / Abstract Base Classes
    |  Domain Concepts (Notebook, Graph, Chunk)
    |  Concrete Implementations
    |  External Libraries (nbformat, networkx)
    ↓
Least Stable (Concrete)
```

### Current Dependencies

| Class | Depends On | Stability | Grade |
|-------|-----------|-----------|-------|
| `JupyterExtractor` | `ASTChunkBuilder`, `TreeSitterChunker` | Unstable (concrete) | D |
| `ObsidianExtractor` | `ObsidianGraphBuilder` | Unstable (concrete) | C |
| `ObsidianGraphBuilder` | `networkx.DiGraph` | Stable (library) | B+ |
| `GraphRepository` | `sqlite3` | Stable (stdlib) | A |

### Recommended Abstraction Layers

```python
# STABLE ABSTRACTIONS (depend on these)
class ChunkerInterface(ABC):
    """Stable abstraction for all chunking strategies"""
    @abstractmethod
    def chunkify(self, source: str) -> List[Chunk]:
        pass

class GraphBuilderInterface(ABC):
    """Stable abstraction for graph construction"""
    @abstractmethod
    def add_note(self, note_id: str, content: str):
        pass

# CONCRETE IMPLEMENTATIONS (inject these)
class ASTChunker(ChunkerInterface):
    """Wraps ASTChunkBuilder"""

class TreeSitterChunker(ChunkerInterface):
    """Wraps TreeSitterChunker"""

# USAGE (depend on abstractions)
class JupyterExtractor:
    def __init__(self, chunker: ChunkerInterface):
        self.chunker = chunker  # ✓ Depends on stable abstraction
```

---

## 7. Liskov Substitution Principle Violations

### Core Principle (from POODR)
> "Subtypes must be substitutable for their supertypes. Objects that include modules can be trusted to interchangeably play the module's role."

### Violation: Inconsistent Return Types

**graph_repository.py (get_connected_nodes_multi_hop):**
```python
def get_connected_nodes_multi_hop(self, start_node_id: str, hops: int = 2):
    """Returns different structures depending on hops parameter"""
    if hops == 1:
        return self.get_simple_neighbors(start_node_id)  # Returns List[str]
    else:
        return self._complex_traversal(...)  # Returns Dict[str, Set]
```

**Issue:** Return type varies based on input
- Caller must know implementation details
- Cannot substitute different hop strategies
- Violates contract expectations

**Fix:**
```python
def get_connected_nodes_multi_hop(self, start_node_id: str, hops: int = 2) -> Set[str]:
    """Always returns Set[str] - consistent contract"""
    # Normalize all return paths to same type
```

---

## 8. Testing Implications (POODR Chapter 9)

### Current Testability

| Module | Testability | Issues |
|--------|-------------|--------|
| `jupyter_extractor.py` | Low | Concrete dependencies, no injection |
| `obsidian_extractor.py` | Medium | Can mock graph_builder if injected |
| `obsidian_graph.py` | High | Clean interfaces, minimal coupling |
| `graph_repository.py` | Medium | Requires DB, complex state |

### Making Code Testable

**Before (untestable):**
```python
class JupyterExtractor:
    def _chunk_code_cell(self, cell, language, filepath):
        from astchunk import ASTChunkBuilder  # ← Cannot mock!
        chunker = ASTChunkBuilder(...)
```

**After (testable):**
```python
class JupyterExtractor:
    def __init__(self, chunker_factory=None):
        self.chunker_factory = chunker_factory or DefaultFactory()

    def _chunk_code_cell(self, cell, language, filepath):
        chunker = self.chunker_factory.create(language)  # ← Mockable!

# Test
def test_chunk_code_cell():
    mock_factory = Mock()
    mock_factory.create.return_value = MockChunker()

    extractor = JupyterExtractor(chunker_factory=mock_factory)
    result = extractor._chunk_code_cell(...)

    assert mock_factory.create.called_with('python')
```

---

## 9. Refactoring Priorities (POODR-Informed)

### High Priority (Breaking Design Principles)

1. **Extract ChunkerFactory (jupyter_extractor.py)**
   - **Issue:** Concrete dependencies on ASTChunkBuilder, TreeSitterChunker
   - **Fix:** Dependency injection + factory pattern
   - **Benefit:** Testable, extensible, follows Open/Closed
   - **Effort:** 4 hours

2. **Inject GraphBuilder (obsidian_extractor.py)**
   - **Issue:** Creates own ObsidianGraphBuilder
   - **Fix:** Constructor injection
   - **Benefit:** Testable, reusable
   - **Effort:** 1 hour

3. **Split God Classes (all extractors)**
   - **Issue:** 7+ responsibilities per class
   - **Fix:** Extract specialized classes
   - **Benefit:** SRP compliance, maintainability
   - **Effort:** 2-3 days

### Medium Priority (Code Quality)

4. **Define Public Interfaces (graph_repository.py)**
   - **Issue:** Unclear public vs private methods
   - **Fix:** Explicit interface documentation
   - **Benefit:** Clear contracts, safer usage
   - **Effort:** 2 hours

5. **Introduce Duck Types (cell chunking)**
   - **Issue:** Conditional logic based on cell types
   - **Fix:** Chunkable duck type with polymorphism
   - **Benefit:** Eliminate conditionals, extensibility
   - **Effort:** 4 hours

### Low Priority (Polish)

6. **Normalize Return Types (Liskov compliance)**
   - **Issue:** Inconsistent return types
   - **Fix:** Consistent contracts across methods
   - **Benefit:** Predictable behavior
   - **Effort:** 2 hours

---

## 10. POODR Design Patterns Opportunities

### Pattern 1: Template Method (Already Used!)

**obsidian_graph.py** uses template method pattern well:
```python
def add_note(self, ...):
    """Template: Define algorithm steps"""
    self._add_note_node(...)
    self._extract_and_add_wikilinks(...)
    self._extract_and_add_tags(...)
    self._extract_and_add_headers(...)
```

✓ Good use of POODR's recommended pattern!

### Pattern 2: Strategy (Missing)

**Opportunity:** Language-specific chunking strategies
```python
class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, source: str) -> List[Dict]:
        pass

class PythonChunkingStrategy(ChunkingStrategy):
    def chunk(self, source: str) -> List[Dict]:
        # Use ASTChunkBuilder

class RChunkingStrategy(ChunkingStrategy):
    def chunk(self, source: str) -> List[Dict]:
        # Use TreeSitterChunker

class JupyterExtractor:
    def __init__(self, strategy_factory):
        self.strategy_factory = strategy_factory

    def _chunk_code_cell(self, cell, language, filepath):
        strategy = self.strategy_factory.get_strategy(language)
        return strategy.chunk(cell.source)
```

### Pattern 3: Repository (Already Used!)

**graph_repository.py** implements repository pattern:
- ✓ Abstracts persistence layer
- ✓ Hides SQL details
- ⚠️ Could improve with explicit interfaces

---

## 11. Key Takeaways from POODR

### Critical Insights from Your Knowledge Base

1. **"Design is about managing dependencies"**
   - Your code has 4 concrete dependencies that should be injected
   - This is the #1 priority for refactoring

2. **"The best design is loosely coupled"**
   - Law of Demeter: ✓ Excellent compliance!
   - Dependency injection: ❌ Needs work
   - Interface design: ⚠️ Inconsistent

3. **"Ask for what you want, don't tell how to do it"**
   - Several "tell, don't ask" violations in enrichment logic
   - Move behavior into objects that own the data

4. **"Duck typing relies on trusting your ducks"**
   - Missing polymorphic opportunities (Chunkable, Persistable)
   - Could eliminate many conditionals

5. **"Tests are the canary in the coal mine"**
   - Hard-to-test code reveals design problems
   - Concrete dependencies make testing difficult

---

## 12. Action Plan

### Phase 1: Fix Dependencies (Critical)
```
Priority: HIGH
Effort: 1-2 days
Impact: Enables testing, improves flexibility

Tasks:
- [ ] Extract ChunkerFactory interface
- [ ] Inject GraphBuilder in ObsidianExtractor
- [ ] Create abstract base classes for chunking strategies
- [ ] Add factory pattern for chunker creation
```

### Phase 2: Split Responsibilities (Important)
```
Priority: MEDIUM-HIGH
Effort: 3-5 days
Impact: Long-term maintainability

Tasks:
- [ ] Extract OutputParser from JupyterExtractor
- [ ] Extract LanguageDetector from JupyterExtractor
- [ ] Split GraphRepository into Node/Edge/Metadata repos
- [ ] Create CellChunker hierarchy (Strategy pattern)
```

### Phase 3: Introduce Duck Types (Enhancement)
```
Priority: MEDIUM
Effort: 2-3 days
Impact: Eliminate conditionals, increase extensibility

Tasks:
- [ ] Define Chunkable duck type
- [ ] Define Persistable duck type
- [ ] Refactor conditionals to polymorphism
- [ ] Document duck type contracts
```

### Phase 4: Clarify Interfaces (Polish)
```
Priority: LOW-MEDIUM
Effort: 1 day
Impact: Safer usage, clearer contracts

Tasks:
- [ ] Document public interfaces
- [ ] Mark private methods consistently
- [ ] Create interface diagrams
- [ ] Write usage examples
```

---

## Conclusion

Your v0.9.0 code demonstrates **good instincts** (Law of Demeter compliance, reasonable organization) but suffers from **tight coupling** due to concrete dependencies and lack of dependency injection. The code works, but it's harder to test, extend, and reuse than it needs to be.

**The good news:** These are all fixable with refactoring. The architecture is sound—you just need to:
1. Inject dependencies instead of creating them
2. Depend on abstractions instead of concretions
3. Split large classes into focused collaborators
4. Use duck typing to eliminate conditionals

**POODR Grade: B-**
- Functional and maintainable, but not optimally designed
- Low coupling in some areas (Demeter), high in others (dependencies)
- Needs refactoring to achieve "exemplary" status

**Recommended Next Read:** Review POODR Chapter 3 (Managing Dependencies) and Chapter 5 (Duck Typing) from your knowledge base before starting refactoring.

---

*POODR Audit completed: 2025-11-19*
*Based on: Practical Object-Oriented Design in Ruby (Sandi Metz)*
*Knowledge Base: 99Bottles + POODR principles*
