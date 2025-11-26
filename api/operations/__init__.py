# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Operations layer for RAG system.

This package handles API-facing operations:
- Query execution (QueryExecutor)
- Document listing/searching (DocumentLister, DocumentSearcher)
- File discovery (FileWalker)
- Index orchestration (IndexOrchestrator)
- Integrity analysis (CompletenessAnalyzer, CompletenessReporter)
- Orphan detection (OrphanDetector)

Following Sandi Metz principles:
- Single Responsibility Principle
- Dependency Injection
"""
