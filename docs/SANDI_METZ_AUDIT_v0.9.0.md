# Sandi Metz Code Quality Audit - v0.9.0-alpha

**Date:** 2025-11-19
**Release:** v0.9.0-alpha (Jupyter + Obsidian Graph-RAG)
**Audited Modules:** New features from v0.9.0 release

---

## Executive Summary

This audit evaluates the new Jupyter and Obsidian Graph-RAG modules against **Sandi Metz's Object-Oriented Design Rules** and industry-standard code quality metrics (Cyclomatic Complexity, ABC Metric, Maintainability Index).

### Overall Assessment

**Maintainability Grade:** A (Average 55.25/100)
**Cyclomatic Complexity:** A (Average 3.23)
**Sandi Metz Compliance:** 74 violations across 5 modules

### Key Findings

✅ **Strengths:**
- Excellent maintainability scores (all modules rated A)
- Low cyclomatic complexity (average 3.23 - well below threshold of 10)
- Clean module boundaries and single responsibility
- Strong cohesion within graph and extraction logic

⚠️ **Critical Issues:**
- **4 "God Classes"** exceeding 100 lines (max violation: 467 lines)
- **3 high-complexity methods** rated C (CC 12-17)
- **70+ method-level violations** (mostly exceeding 5-line limit)
- **8 parameter violations** (5-6 parameters vs max 4)

---

## Metrics Overview

### 1. Maintainability Index (radon mi)

| Module | Score | Grade | Assessment |
|--------|-------|-------|------------|
| `jupyter_extractor.py` | 47.87 | A | Excellent |
| `obsidian_extractor.py` | 53.27 | A | Excellent |
| `obsidian_graph.py` | 46.33 | A | Excellent |
| `obsidian_detector.py` | 76.67 | A | Outstanding |
| `graph_repository.py` | 52.11 | A | Excellent |
| **Average** | **55.25** | **A** | **Excellent** |

**Interpretation:** All modules achieve A-grade maintainability (threshold: >20). The `obsidian_detector.py` achieves exceptional score of 76.67, indicating very low maintenance burden.

---

### 2. Cyclomatic Complexity (radon cc)

**Scale:** A (1-5) | B (6-10) | C (11-20) | D (21-50) | F (51+)

#### High-Risk Methods (Grade C - Needs Refactoring)

| File | Method | CC | Grade | Line Count |
|------|--------|----|----|------------|
| `jupyter_extractor.py` | `_parse_outputs` | **17** | C | 55 lines |
| `jupyter_extractor.py` | `_chunk_code_cell` | **12** | C | 123 lines |
| `obsidian_extractor.py` | `_chunk_semantically` | **16** | C | 72 lines |

**Risk Analysis:**
- **CC 12-17** indicates complex branching logic
- High test coverage required (12-17 unique paths per method)
- Refactoring recommended to improve testability

#### Moderate Complexity (Grade B)

| File | Method | CC | Grade |
|------|--------|----|-------|
| `jupyter_extractor.py` | `JupyterExtractor` (class) | 10 | B |
| `jupyter_extractor.py` | `_combine_adjacent_cells` | 10 | B |
| `jupyter_extractor.py` | `_parse_notebook` | 8 | B |
| `jupyter_extractor.py` | `_merge_chunk_group` | 8 | B |
| `jupyter_extractor.py` | `extract` | 7 | B |
| `obsidian_extractor.py` | `_enrich_chunks_with_graph` | 8 | B |
| `graph_repository.py` | `persist_graph` | 8 | B |

**Total:** 90 methods analyzed, 3 critical (C), 7 moderate (B), 80 simple (A)

---

## Sandi Metz Rules Violations

### The Four Rules

1. **Classes can be no longer than 100 lines of code**
2. **Methods can be no longer than 5 lines of code**
3. **Pass no more than 4 parameters into a method**
4. **Controllers can instantiate only one object** (N/A for this codebase)

### Violation Summary

| Rule | Violations | Severity |
|------|-----------|----------|
| **Rule 1: Classes ≤ 100 lines** | **4** | 🔴 Critical |
| **Rule 2: Methods ≤ 5 lines** | **62** | 🟡 High |
| **Rule 3: Parameters ≤ 4** | **8** | 🟠 Medium |
| **Total Violations** | **74** | - |

---

### Rule 1: Class Size Violations (4 violations)

| Class | Lines | Violation % | File |
|-------|-------|-------------|------|
| `JupyterExtractor` | **467** | +367% | jupyter_extractor.py |
| `ObsidianGraphBuilder` | **320** | +220% | obsidian_graph.py |
| `GraphRepository` | **386** | +286% | graph_repository.py |
| `ObsidianExtractor` | **237** | +137% | obsidian_extractor.py |

**Impact:**
- **God Class anti-pattern** - classes have too many responsibilities
- Difficult to test in isolation
- High coupling, low cohesion
- Violates Single Responsibility Principle (SRP)

**Recommended Actions:**
1. **JupyterExtractor (467 lines)** → Extract:
   - `OutputParser` (handles `_parse_outputs`)
   - `CodeCellChunker` (handles `_chunk_code_cell`)
   - `NotebookReader` (handles `_parse_notebook`)

2. **ObsidianGraphBuilder (320 lines)** → Extract:
   - `GraphNodeFactory` (node creation methods)
   - `GraphEdgeFactory` (edge creation methods)
   - `GraphAnalyzer` (PageRank, stats, export)

3. **GraphRepository (386 lines)** → Extract:
   - `NodeRepository` (node CRUD)
   - `EdgeRepository` (edge CRUD)
   - `GraphCleanupService` (orphan cleanup, deletion logic)

4. **ObsidianExtractor (237 lines)** → Extract:
   - `FrontmatterParser`
   - `GraphEnricher`
   - `SemanticChunker`

---

### Rule 2: Method Length Violations (62 violations)

**Critical Long Methods (>50 lines):**

| Method | Lines | CC | File |
|--------|-------|----|------|
| `_chunk_code_cell` | **123** | 12 | jupyter_extractor.py |
| `extract` | **58** | 7 | jupyter_extractor.py |
| `_combine_adjacent_cells` | **57** | 10 | jupyter_extractor.py |
| `_parse_notebook` | **56** | 8 | jupyter_extractor.py |
| `_parse_outputs` | **55** | 17 | jupyter_extractor.py |
| `_chunk_semantically` | **72** | 16 | obsidian_extractor.py |
| `update_note_path` | **45** | 4 | graph_repository.py |
| `_enrich_chunks_with_graph` | **41** | 8 | obsidian_extractor.py |

**Analysis:**
- **Jupyter methods:** Dominated by conditional parsing logic (Python vs R, AST vs fallback)
- **Obsidian methods:** Complex chunking with overlap and graph enrichment
- **Graph methods:** SQL-heavy with multiple transaction steps

**Refactoring Strategy:**
- Extract conditional branches into strategy pattern
- Use polymorphism for language-specific chunking (PythonChunker, RChunker)
- Extract SQL queries into repository methods
- Break complex methods into pipelines

---

### Rule 3: Parameter Count Violations (8 violations)

| Method | Params | File |
|--------|--------|------|
| `save_node` | **6** | graph_repository.py |
| `add_note` | **5** | obsidian_graph.py |
| `_add_note_node` | **5** | obsidian_graph.py |
| `_add_header_node` | **5** | obsidian_graph.py |
| `save_edge` | **5** | graph_repository.py |
| `_enrich_chunks_with_graph` | **5** | obsidian_extractor.py |

**Impact:**
- High cognitive load for callers
- Difficult to remember parameter order
- Suggests missing domain objects

**Recommended Actions:**
1. **Introduce parameter objects:**
   ```python
   # Before: save_node(node_id, node_type, title, content, metadata, extra)
   # After: save_node(node: GraphNode)

   @dataclass
   class GraphNode:
       node_id: str
       node_type: str
       title: str
       content: str
       metadata: Dict
   ```

2. **Builder pattern for complex creation:**
   ```python
   node = GraphNodeBuilder()\
       .with_id(node_id)\
       .with_type(node_type)\
       .with_title(title)\
       .build()
   ```

---

## Detailed Module Analysis

### 1. jupyter_extractor.py (499 lines)

**Metrics:**
- Maintainability: A (47.87)
- Average CC: 3.23
- Class violations: 1 (467 lines)
- Method violations: 9

**Code Smells:**
- **Feature Envy:** `_chunk_code_cell` knows too much about astchunk and TreeSitterChunker
- **Long Method:** Multiple 50+ line methods with nested try/except blocks
- **Duplicate Code:** Python and R chunking logic nearly identical (lines 208-289)

**Refactoring Priority:** 🔴 High

**Suggested Refactorings:**
1. Extract `OutputParser` class
2. Use Strategy pattern for language-specific chunking:
   ```python
   class ChunkingStrategy(ABC):
       @abstractmethod
       def chunk(self, cell: NotebookCell) -> List[Dict]:
           pass

   class PythonChunkingStrategy(ChunkingStrategy):
       # Uses astchunk

   class RChunkingStrategy(ChunkingStrategy):
       # Uses TreeSitterChunker

   class DefaultChunkingStrategy(ChunkingStrategy):
       # Cell-level chunking
   ```

---

### 2. obsidian_extractor.py (321 lines)

**Metrics:**
- Maintainability: A (53.27)
- Average CC: 3.0
- Class violations: 1 (237 lines)
- Method violations: 11

**Code Smells:**
- **Long Method:** `_chunk_semantically` (72 lines, CC 16)
- **Complex Conditionals:** Header detection and overlap calculation
- **Feature Envy:** Knows too much about ObsidianGraphBuilder internals

**Refactoring Priority:** 🟡 Medium

**Suggested Refactorings:**
1. Extract `SemanticChunker` with dedicated responsibility
2. Extract `GraphMetadataEnricher` for graph enrichment logic
3. Replace complex conditionals with guard clauses
4. Use value objects for chunk boundaries

---

### 3. obsidian_graph.py (367 lines)

**Metrics:**
- Maintainability: A (46.33)
- Average CC: 2.8
- Class violations: 1 (320 lines)
- Method violations: 21

**Code Smells:**
- **Too Many Responsibilities:** Node creation, edge creation, graph traversal, PageRank, export
- **Primitive Obsession:** Strings used for node_type instead of enum
- **Data Clumps:** (node_id, node_type, title, content) appear together frequently

**Refactoring Priority:** 🟠 Medium-High

**Suggested Refactorings:**
1. Split into 3 classes:
   - `GraphBuilder` (construction)
   - `GraphAnalyzer` (queries, PageRank)
   - `GraphSerializer` (import/export)
2. Introduce enum for node types and edge types:
   ```python
   class NodeType(Enum):
       NOTE = "note"
       TAG = "tag"
       HEADER = "header"
       NOTE_REF = "note_ref"
   ```

---

### 4. obsidian_detector.py (98 lines)

**Metrics:**
- Maintainability: A (76.67) ⭐ Outstanding
- Average CC: 4.0
- Class violations: 0
- Method violations: 4

**Code Smells:** None (cleanest module!)

**Refactoring Priority:** 🟢 Low

**Notes:**
- Excellent example of focused responsibility
- Clear detection heuristics
- Well-named methods
- Could be reference implementation for other modules

---

### 5. graph_repository.py (398 lines)

**Metrics:**
- Maintainability: A (52.11)
- Average CC: 2.5
- Class violations: 1 (386 lines)
- Method violations: 21

**Code Smells:**
- **Long Method:** `update_note_path` (45 lines) - complex two-step update logic
- **SQL Injection Risk:** Some methods use string formatting (verify parameterization)
- **Transaction Management:** Mixed commit patterns

**Refactoring Priority:** 🟠 Medium

**Suggested Refactorings:**
1. Split into repositories:
   - `NodeRepository`
   - `EdgeRepository`
   - `GraphMetadataRepository`
   - `ChunkLinkRepository`
2. Extract `GraphCleanupService` for orphan cleanup
3. Use query builder or ORM for complex SQL
4. Consistent transaction boundaries (context managers)

---

## Comparison with Knowledge Base Insights

Based on your RAG knowledge base (Sandi Metz's "99 Bottles of Beer"), here are key insights:

### ABC Metric (Not Run - Recommendation)

The knowledge base emphasizes **ABC (Assignments, Branches, Conditions)** as superior to cyclomatic complexity:

> "ABC is a measure of complexity. Highly complex code is difficult to understand and change, therefore ABC scores are a proxy for code quality."

**Recommendation:** Run `radon raw` to get ABC scores:
```bash
radon raw -s api/ingestion/*.py
```

### Code Quality Philosophy

From your knowledge base:

1. **"Shameless Green" First:**
   > "Make it work, then make it right, then make it fast"

   ✅ Your v0.9.0 code achieves "Shameless Green" - it works!

2. **Metrics vs Opinion:**
   > "Metrics are fallible but human opinion is no more precise"

   ✅ This audit uses objective metrics (CC, MI, SLOC)

3. **When to Tolerate Violations:**
   > "Despite the complexity score, this code is better. An improvement has been made that is invisible to static analysis tools."

   ⚠️ Your code reveals correct abstractions (JupyterExtractor, ObsidianGraphBuilder) but needs further decomposition

---

## Recommended Refactoring Roadmap

### Phase 1: Quick Wins (1-2 days)
- [ ] Fix parameter count violations (introduce parameter objects)
- [ ] Extract enums for node_type and edge_type
- [ ] Add guard clauses to reduce nesting in long methods
- [ ] Extract SQL queries into constants/templates

### Phase 2: Class Decomposition (3-5 days)
- [ ] Split `JupyterExtractor` → `OutputParser`, `CodeCellChunker`, `NotebookReader`
- [ ] Split `ObsidianGraphBuilder` → `GraphBuilder`, `GraphAnalyzer`, `GraphSerializer`
- [ ] Split `GraphRepository` → `NodeRepository`, `EdgeRepository`, `GraphCleanupService`

### Phase 3: Design Patterns (5-7 days)
- [ ] Implement Strategy pattern for language-specific chunking
- [ ] Implement Factory pattern for node/edge creation
- [ ] Implement Builder pattern for complex object construction
- [ ] Add Repository layer abstractions

### Phase 4: Test Coverage (ongoing)
- [ ] Achieve CC coverage: 17 tests for `_parse_outputs`, 12 for `_chunk_code_cell`, etc.
- [ ] Add integration tests for refactored classes
- [ ] Property-based testing for graph operations

---

## Tools and Commands Used

```bash
# Cyclomatic Complexity
radon cc api/ingestion/*.py -a -s

# Maintainability Index
radon mi api/ingestion/*.py -s

# Raw Metrics (recommended for ABC)
radon raw -s api/ingestion/*.py

# Sandi Metz Violations (custom Python script)
python3 sandi_metz_checker.py
```

---

## References

**From Knowledge Base:**
- Sandi Metz, "99 Bottles of Beer" (Python Edition)
- Thomas J. McCabe, "A Complexity Measure" (1976)
- Jerry Fitzpatrick, "Applying the ABC Metric" (1997)

**External:**
- Radon Documentation: https://radon.readthedocs.io/
- Sandi Metz Rules: https://thoughtbot.com/blog/sandi-metz-rules-for-developers

---

## Conclusion

The v0.9.0 codebase demonstrates **strong functional design** with excellent maintainability scores (A grade) and low cyclomatic complexity (3.23 average). However, it suffers from **God Class anti-pattern** and **long methods** that violate Sandi Metz's rules for clean OO design.

**Next Steps:**
1. Run ABC metric analysis for deeper insight
2. Prioritize Phase 1 quick wins
3. Plan Phase 2 class decomposition for next sprint
4. Establish pre-commit hooks for complexity checks

**Overall Grade:** B+ (Functional but needs refactoring for long-term maintainability)

---

*Audit completed: 2025-11-19*
*Auditor: Automated analysis via radon + Sandi Metz rules*
*Next audit: After Phase 2 refactoring completion*
