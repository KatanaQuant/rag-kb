"""Tests for DoclingExtractor - PDF/DOCX extraction with OCR support

TDD approach: Write tests first to specify expected behavior
"""
import pytest
from pathlib import Path

from tests import requires_huggingface
from ingestion.extractors import DoclingExtractor
from ingestion.database import DOCLING_AVAILABLE

class TestDoclingExtractor:
    """Test Docling-based document extraction with OCR"""

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_get_converter_creates_singleton(self):
        """Should create converter only once (singleton pattern)"""
        converter1 = DoclingExtractor.get_converter()
        converter2 = DoclingExtractor.get_converter()

        assert converter1 is not None
        assert converter1 is converter2  # Same instance

    # DELETED: test_converter_supports_ocr_for_images - placeholder test (only checked is not None)
    # DELETED: test_extracts_text_based_pdf_without_ocr_slowdown - placeholder test (only checked is not None)

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    @requires_huggingface
    def test_chunker_uses_hybrid_strategy(self):
        """Should use HybridChunker for token-aware chunking"""
        chunker = DoclingExtractor.get_chunker(max_tokens=512)

        assert chunker is not None
        # Chunker should be reused (singleton)
        chunker2 = DoclingExtractor.get_chunker(max_tokens=512)
        assert chunker is chunker2

# DELETED: TestDoclingOCRConfiguration class - all 3 tests were placeholders (only checked is not None)
# These would need real PDF processing to test meaningfully
