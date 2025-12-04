"""
Extractors package

Modularized extractors following best practices:
- Each extractor in its own file (< 200 lines)
- Single Responsibility Principle
- Easy to test and maintain

Re-exports all extractors for backward compatibility with existing imports:
    from ingestion.extractors import DoclingExtractor, EpubExtractor, etc.

Refactored from monolithic extractors.py (747 LOC → 7 focused modules)
"""
from ingestion.extractors._docling_availability import (
    DOCLING_AVAILABLE,
    DOCLING_CHUNKING_AVAILABLE
)
from ingestion.extractors.docling_extractor import DoclingExtractor
from ingestion.extractors.markdown_extractor import MarkdownExtractor
from ingestion.extractors.epub_extractor import EpubExtractor
from ingestion.extractors.code_extractor import CodeExtractor
from ingestion.extractors.extraction_router import ExtractionRouter

__all__ = [
    'DOCLING_AVAILABLE',
    'DOCLING_CHUNKING_AVAILABLE',
    'DoclingExtractor',
    'MarkdownExtractor',
    'EpubExtractor',
    'CodeExtractor',
    'ExtractionRouter',
]
