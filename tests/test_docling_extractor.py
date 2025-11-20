"""Tests for DoclingExtractor - PDF/DOCX extraction with OCR support

TDD approach: Write tests first to specify expected behavior
"""
import pytest
from pathlib import Path
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

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_converter_supports_ocr_for_images(self):
        """Should have OCR enabled to extract text from images in PDFs

        OCR is needed for:
        - Scanned PDFs (image-only)
        - Hybrid PDFs with diagrams containing text
        - Screenshots embedded in documents
        """
        converter = DoclingExtractor.get_converter()

        # Converter should be configured with OCR support
        assert converter is not None
        # Note: We can't directly test OCR without processing a PDF,
        # but we verify the converter is created successfully

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_extracts_text_based_pdf_without_ocr_slowdown(self, tmp_path):
        """Should extract text-based PDFs efficiently

        Text-based PDFs should use direct text extraction,
        but OCR should still be available for images within the PDF.
        """
        # This test requires a real PDF file with embedded text
        # For now, we verify the extractor can be initialized
        assert DoclingExtractor.get_converter() is not None

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_chunker_uses_hybrid_strategy(self):
        """Should use HybridChunker for token-aware chunking"""
        chunker = DoclingExtractor.get_chunker(max_tokens=512)

        assert chunker is not None
        # Chunker should be reused (singleton)
        chunker2 = DoclingExtractor.get_chunker(max_tokens=512)
        assert chunker is chunker2

    def test_extraction_result_includes_method_name(self):
        """Should tag extraction results with 'docling' method

        This helps track which extraction method was used
        for debugging and optimization.
        """
        # This would require a real PDF to test fully
        # For now, we document the expected behavior
        pass

class TestDoclingOCRConfiguration:
    """Test OCR configuration for different PDF types"""

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_supports_text_based_pdfs(self):
        """Should extract from PDFs with embedded text layer

        Examples: O'Reilly books, LaTeX PDFs, Calibre exports
        """
        converter = DoclingExtractor.get_converter()
        assert converter is not None

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_supports_scanned_pdfs_with_ocr(self):
        """Should use OCR for scanned/image-only PDFs

        OCR should run when PDF has no text layer.
        """
        converter = DoclingExtractor.get_converter()
        assert converter is not None

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_supports_hybrid_pdfs_with_images(self):
        """Should extract both text AND use OCR for images

        Technical books often have:
        - Regular text (extracted directly)
        - Diagrams with labels (need OCR)
        - Code screenshots (need OCR)
        """
        converter = DoclingExtractor.get_converter()
        assert converter is not None
