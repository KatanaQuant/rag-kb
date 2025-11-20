# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Services layer for RAG system.

Following Sandi Metz principles:
- Extract services from god classes
- Single Responsibility Principle
- Dependency Injection
"""

from .logger import Logger
from .embedding_service import EmbeddingService
from .indexing_queue import IndexingQueue, Priority
from .indexing_worker import IndexingWorker

__all__ = ['Logger', 'EmbeddingService', 'IndexingQueue', 'Priority', 'IndexingWorker']
