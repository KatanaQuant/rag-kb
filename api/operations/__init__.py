"""Operations layer for RAG system.

This package handles API-facing operations:
- Query execution (QueryExecutor)
- Document listing/searching (DocumentLister, DocumentSearcher)
- File discovery (FileWalker)
- Index orchestration (IndexOrchestrator)
- Integrity analysis (CompletenessAnalyzer, CompletenessReporter)
- Orphan detection (OrphanDetector)

Principles:
- Single Responsibility Principle
- Dependency Injection
"""
