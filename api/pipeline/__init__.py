"""Pipeline layer for RAG system.

This package handles background document processing:
- Embedding generation (EmbeddingService)
- Indexing queue management (IndexingQueue)
- Background workers (IndexingWorker)
- Pipeline coordination (PipelineCoordinator)
- Security scanning (QuarantineManager)

Principles:
- Single Responsibility Principle
- Dependency Injection
"""

from .logger import Logger
from .embedding_service import EmbeddingService
from .indexing_queue import IndexingQueue, Priority
from .indexing_worker import IndexingWorker

__all__ = ['Logger', 'EmbeddingService', 'IndexingQueue', 'Priority', 'IndexingWorker']
