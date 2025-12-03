"""Pipeline interfaces for modular RAG-KB architecture.

Provides abstract base classes for pipeline components:
- ExtractorInterface: Document text extraction
- ChunkerInterface: Text chunking strategies
- EmbedderInterface: Text embedding generation
- RerankerInterface: Search result reranking

Following Sandi Metz POODR principles:
- Depend on abstractions, not concretions
- Single responsibility per interface
- Message-based coupling via data contracts
"""

from pipeline.interfaces.extractor import ExtractorInterface
from pipeline.interfaces.chunker import ChunkerInterface
from pipeline.interfaces.embedder import EmbedderInterface
from pipeline.interfaces.reranker import RerankerInterface, NoopReranker

__all__ = [
    'ExtractorInterface',
    'ChunkerInterface',
    'EmbedderInterface',
    'RerankerInterface',
    'NoopReranker',
]
