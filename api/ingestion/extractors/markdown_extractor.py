"""
Markdown file extractor

Extracts text from Markdown files using Docling HybridChunker.
Extracted from extractors.py during modularization refactoring.
"""
from pathlib import Path
from domain_models import ExtractionResult
from ingestion.extractors._docling_availability import (
    DOCLING_AVAILABLE,
    DOCLING_CHUNKING_AVAILABLE
)


class MarkdownExtractor:
    """Extracts text from Markdown files using Docling HybridChunker

    NO FALLBACKS: Fails explicitly if Docling is unavailable or fails.
    """

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract markdown using Docling converter + HybridChunker

        NO FALLBACKS: Raises exceptions if Docling is unavailable or fails.

        Returns:
            ExtractionResult with Docling HybridChunker pages

        Raises:
            RuntimeError: If Docling or HybridChunker is unavailable
            Exception: If conversion fails
        """
        if not DOCLING_AVAILABLE:
            raise RuntimeError(
                f"Docling not available for markdown extraction: {path.name}\n"
                "Install docling to enable markdown processing."
            )

        if not DOCLING_CHUNKING_AVAILABLE:
            raise RuntimeError(
                f"Docling HybridChunker not available for markdown extraction: {path.name}\n"
                "Upgrade to docling>=2.9.0 to enable markdown processing."
            )

        # Import DoclingExtractor here to avoid circular import
        from ingestion.extractors.docling_extractor import DoclingExtractor

        # NO try-except: Let conversion errors propagate
        converter = DoclingExtractor.get_converter()
        result = converter.convert(str(path))

        document = result.document
        pages = DoclingExtractor._extract_hybrid_chunks(document)
        return ExtractionResult(pages=pages, method='docling_markdown')
