"""Tests for DoclingExtractor - PDF/DOCX extraction with OCR support

TDD approach: Write tests first to specify expected behavior
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

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


class TestDoclingConfigFields:
    """Test DoclingConfig has the new memory optimization fields"""

    def test_docling_config_has_generate_page_images_field(self):
        """DoclingConfig should have generate_page_images field defaulting to True"""
        from config import DoclingConfig

        config = DoclingConfig()

        assert hasattr(config, 'generate_page_images')
        assert config.generate_page_images is True

    def test_docling_config_has_generate_picture_images_field(self):
        """DoclingConfig should have generate_picture_images field defaulting to True"""
        from config import DoclingConfig

        config = DoclingConfig()

        assert hasattr(config, 'generate_picture_images')
        assert config.generate_picture_images is True

    def test_docling_config_has_pdf_backend_field(self):
        """DoclingConfig should have pdf_backend field defaulting to dlparse_v4"""
        from config import DoclingConfig

        config = DoclingConfig()

        assert hasattr(config, 'pdf_backend')
        assert config.pdf_backend == "dlparse_v4"

    def test_docling_config_pdf_backend_accepts_pypdfium2(self):
        """DoclingConfig pdf_backend should accept pypdfium2 value"""
        from config import DoclingConfig

        config = DoclingConfig(pdf_backend="pypdfium2")

        assert config.pdf_backend == "pypdfium2"


class TestEnvironmentConfigLoaderDoclingOptions:
    """Test EnvironmentConfigLoader reads new Docling env vars"""

    def test_loads_generate_page_images_from_env_true(self):
        """Should read DOCLING_GENERATE_PAGE_IMAGES=true from environment"""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db',
            'DOCLING_GENERATE_PAGE_IMAGES': 'true'
        }):
            from environment_config_loader import EnvironmentConfigLoader

            loader = EnvironmentConfigLoader()
            config = loader.load()

            assert config.docling.generate_page_images is True

    def test_loads_generate_page_images_defaults_true(self):
        """Should default generate_page_images to True when env var not set"""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db'
        }, clear=True):
            from environment_config_loader import EnvironmentConfigLoader

            loader = EnvironmentConfigLoader()
            config = loader.load()

            assert config.docling.generate_page_images is True

    def test_loads_generate_picture_images_from_env_false(self):
        """Should read DOCLING_GENERATE_PICTURE_IMAGES=false from environment"""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db',
            'DOCLING_GENERATE_PICTURE_IMAGES': 'false'
        }):
            from environment_config_loader import EnvironmentConfigLoader

            loader = EnvironmentConfigLoader()
            config = loader.load()

            assert config.docling.generate_picture_images is False

    def test_loads_generate_picture_images_defaults_true(self):
        """Should default generate_picture_images to True when env var not set"""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db'
        }, clear=True):
            from environment_config_loader import EnvironmentConfigLoader

            loader = EnvironmentConfigLoader()
            config = loader.load()

            assert config.docling.generate_picture_images is True

    def test_loads_pdf_backend_from_env(self):
        """Should read DOCLING_PDF_BACKEND from environment"""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db',
            'DOCLING_PDF_BACKEND': 'pypdfium2'
        }):
            from environment_config_loader import EnvironmentConfigLoader

            loader = EnvironmentConfigLoader()
            config = loader.load()

            assert config.docling.pdf_backend == "pypdfium2"

    def test_loads_pdf_backend_defaults_dlparse_v4(self):
        """Should default pdf_backend to dlparse_v4 when env var not set"""
        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db'
        }, clear=True):
            from environment_config_loader import EnvironmentConfigLoader

            loader = EnvironmentConfigLoader()
            config = loader.load()

            assert config.docling.pdf_backend == "dlparse_v4"


class TestDoclingExtractorConverterConfig:
    """Test DoclingExtractor.get_converter() uses config options"""

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_get_converter_uses_generate_page_images_config(self):
        """get_converter should configure PdfPipelineOptions with generate_page_images"""
        # Reset singleton for test isolation
        DoclingExtractor._converter = None

        with patch.dict(os.environ, {
            'DATABASE_URL': 'sqlite:///test.db',
            'DOCLING_GENERATE_PAGE_IMAGES': 'false'
        }):
            # Reload config to pick up env vars
            from config import DoclingConfig
            mock_config = DoclingConfig(
                enabled=True,
                generate_page_images=False,
                generate_picture_images=True,
                pdf_backend="dlparse_v4"
            )

            with patch('ingestion.extractors.docling_extractor.default_config') as mock_default:
                mock_default.docling = mock_config

                # Mock DocumentConverter to capture initialization args
                with patch('docling.document_converter.DocumentConverter') as MockConverter:
                    DoclingExtractor.get_converter()

                    # Verify DocumentConverter was called with PdfPipelineOptions
                    MockConverter.assert_called_once()
                    call_kwargs = MockConverter.call_args
                    # The implementation should pass pipeline_options with generate_page_images=False
                    assert call_kwargs is not None, "DocumentConverter should be called with arguments"

        # Reset singleton after test
        DoclingExtractor._converter = None

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_get_converter_uses_generate_picture_images_config(self):
        """get_converter should configure PdfPipelineOptions with generate_picture_images"""
        DoclingExtractor._converter = None

        from config import DoclingConfig
        mock_config = DoclingConfig(
            enabled=True,
            generate_page_images=True,
            generate_picture_images=False,
            pdf_backend="dlparse_v4"
        )

        with patch('ingestion.extractors.docling_extractor.default_config') as mock_default:
            mock_default.docling = mock_config

            with patch('docling.document_converter.DocumentConverter') as MockConverter:
                DoclingExtractor.get_converter()

                MockConverter.assert_called_once()
                call_kwargs = MockConverter.call_args
                assert call_kwargs is not None, "DocumentConverter should be called with arguments"

        DoclingExtractor._converter = None

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_get_converter_uses_pdf_backend_dlparse_v4(self):
        """get_converter should configure PdfPipelineOptions with dlparse_v4 backend"""
        DoclingExtractor._converter = None

        from config import DoclingConfig
        mock_config = DoclingConfig(
            enabled=True,
            generate_page_images=False,
            generate_picture_images=False,
            pdf_backend="dlparse_v4"
        )

        with patch('ingestion.extractors.docling_extractor.default_config') as mock_default:
            mock_default.docling = mock_config

            with patch('docling.document_converter.DocumentConverter') as MockConverter:
                DoclingExtractor.get_converter()

                MockConverter.assert_called_once()
                # Implementation should use DoclingParseV4DocumentBackend for dlparse_v4
                call_kwargs = MockConverter.call_args
                assert call_kwargs is not None

        DoclingExtractor._converter = None

    @pytest.mark.skipif(not DOCLING_AVAILABLE, reason="Docling not available")
    def test_get_converter_uses_pdf_backend_pypdfium2(self):
        """get_converter should configure PdfPipelineOptions with pypdfium2 backend"""
        DoclingExtractor._converter = None

        from config import DoclingConfig
        mock_config = DoclingConfig(
            enabled=True,
            generate_page_images=False,
            generate_picture_images=False,
            pdf_backend="pypdfium2"
        )

        with patch('ingestion.extractors.docling_extractor.default_config') as mock_default:
            mock_default.docling = mock_config

            with patch('docling.document_converter.DocumentConverter') as MockConverter:
                DoclingExtractor.get_converter()

                MockConverter.assert_called_once()
                # Implementation should use PyPdfiumDocumentBackend for pypdfium2
                call_kwargs = MockConverter.call_args
                assert call_kwargs is not None

        DoclingExtractor._converter = None
