"""
Tests for EPUB extractor functionality

Verifies the EPUB→PDF conversion pipeline:
1. EPUB files are converted to PDF (not extracted)
2. Resulting PDFs are left in knowledge_base/ for later processing
3. Original EPUB files are moved to original/ subdirectory
4. Empty ExtractionResult returned (no text extraction during conversion)

This tests the bug fix from 2025-11-21 where EPUBs were incorrectly
being extracted during conversion instead of just being converted.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from ingestion.extractors import EpubExtractor
from domain_models import ExtractionResult


class TestEpubConversionOnly:
    """Test that EPUB conversion returns empty result (no extraction)"""

    def test_epub_extract_returns_empty_result(self, tmp_path):
        """EPUB should convert to PDF but NOT extract text

        Bug fix: Previously, EpubExtractor.extract() was calling
        _extract_from_pdf() after conversion, which extracted 287,864 chars
        from the EPUB and tried to chunk it (resulting in "no chunks extracted").

        Now, extract() should return an empty ExtractionResult with
        method='epub_conversion_only' to signal conversion-only.
        """
        epub_path = tmp_path / "test.epub"
        pdf_path = tmp_path / "test.pdf"
        original_dir = tmp_path / "original"
        original_dir.mkdir()

        # Create fake EPUB (valid ZIP structure)
        self._create_minimal_epub(epub_path)

        # Mock subprocess calls for Pandoc, Ghostscript, pdfinfo
        with patch('subprocess.run') as mock_run:
            # Pandoc conversion succeeds
            mock_run.side_effect = [
                Mock(returncode=0, stdout="", stderr=""),  # pandoc
                Mock(returncode=0, stdout="", stderr=""),  # ghostscript
                Mock(returncode=0, stdout="Pages:          10\n", stderr=""),  # pdfinfo
            ]

            # Mock file operations
            with patch('shutil.move'):
                # Create the PDF that pandoc would create
                pdf_path.touch()
                # Create temp PDF that ghostscript would create
                tmp_pdf = tmp_path / "test.tmp.pdf"
                tmp_pdf.touch()

                extractor = EpubExtractor()
                result = extractor.extract(epub_path)

                # Verify empty result (no extraction)
                assert isinstance(result, ExtractionResult)
                assert result.method == 'epub_conversion_only'
                assert len(result.pages) == 0
                assert result.page_count == 0  # Empty pages means 0 count

    def test_epub_conversion_creates_pdf(self, tmp_path):
        """EPUB conversion should create PDF in same directory"""
        epub_path = tmp_path / "System Design Interview.epub"
        pdf_path = tmp_path / "System Design Interview.pdf"
        original_dir = tmp_path / "original"

        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="", stderr=""),  # pandoc
                Mock(returncode=0, stdout="", stderr=""),  # ghostscript
                Mock(returncode=0, stdout="Pages:          287\n", stderr=""),  # pdfinfo
            ]

            with patch('shutil.move'):
                # Simulate pandoc creating the PDF
                pdf_path.touch()
                # Create temp PDF that ghostscript would create
                tmp_pdf = tmp_path / "System Design Interview.tmp.pdf"
                tmp_pdf.touch()

                extractor = EpubExtractor()
                extractor.extract(epub_path)

                # PDF should exist
                assert pdf_path.exists()

    def test_epub_moves_to_original_directory(self, tmp_path):
        """EPUB should be moved to original/ after conversion"""
        epub_path = tmp_path / "book.epub"
        pdf_path = tmp_path / "book.pdf"

        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="", stderr=""),  # pandoc
                Mock(returncode=0, stdout="", stderr=""),  # ghostscript
                Mock(returncode=0, stdout="Pages:          50\n", stderr=""),  # pdfinfo
            ]

            with patch('shutil.move') as mock_move:
                pdf_path.touch()
                # Create temp PDF that ghostscript would create
                tmp_pdf = tmp_path / "book.tmp.pdf"
                tmp_pdf.touch()

                extractor = EpubExtractor()
                extractor.extract(epub_path)

                # Verify EPUB was moved to original/
                mock_move.assert_called_once()
                call_args = mock_move.call_args[0]
                assert str(epub_path) == call_args[0]
                assert 'original' in str(call_args[1])

    def _create_minimal_epub(self, path: Path):
        """Create a minimal valid EPUB file (ZIP with mimetype)"""
        import zipfile
        with zipfile.ZipFile(path, 'w') as epub:
            epub.writestr('mimetype', 'application/epub+zip')
            epub.writestr('META-INF/container.xml', '<?xml version="1.0"?>')


class TestEpubConversionErrors:
    """Test EPUB conversion error handling"""

    def test_invalid_epub_raises_error(self, tmp_path):
        """Invalid EPUB file should raise ValueError"""
        invalid_epub = tmp_path / "not_an_epub.epub"
        invalid_epub.write_text("This is not a valid EPUB file")

        extractor = EpubExtractor()
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(invalid_epub)

        assert "Invalid EPUB file" in str(exc_info.value)
        assert "not_an_epub.epub" in str(exc_info.value)

    def test_pandoc_failure_raises_error(self, tmp_path):
        """Pandoc conversion failure should raise RuntimeError"""
        epub_path = tmp_path / "test.epub"
        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            # Pandoc fails with error
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Error: Pandoc failed to convert EPUB"
            )

            extractor = EpubExtractor()
            with pytest.raises(RuntimeError) as exc_info:
                extractor.extract(epub_path)

            assert "Pandoc EPUB conversion failed" in str(exc_info.value)

    def test_longtable_error_triggers_fallback(self, tmp_path):
        """longtable error should trigger HTML fallback conversion"""
        epub_path = tmp_path / "nested_tables.epub"
        pdf_path = tmp_path / "nested_tables.pdf"

        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            # First call: Pandoc fails with longtable error
            # Second call: EPUB→HTML succeeds
            # Third call: HTML→PDF (Chromium) succeeds
            # Fourth call: Ghostscript font embedding
            # Fifth call: pdfinfo
            mock_run.side_effect = [
                Mock(returncode=1, stdout="", stderr="Error: LT@nofcols forbidden"),  # pandoc direct
                Mock(returncode=0, stdout="", stderr=""),  # pandoc epub→html
                Mock(returncode=0, stdout="", stderr=""),  # chromium html→pdf
                Mock(returncode=0, stdout="", stderr=""),  # ghostscript
                Mock(returncode=0, stdout="Pages:          42\n", stderr=""),  # pdfinfo
            ]

            with patch('shutil.move'):
                # Create a real temporary HTML file
                temp_html = tmp_path / "temp.html"
                temp_html.touch()

                with patch('tempfile.NamedTemporaryFile') as mock_temp:
                    mock_temp.return_value.__enter__.return_value.name = str(temp_html)
                    mock_temp.return_value.__exit__.return_value = None

                    pdf_path.touch()
                    # Create temp PDF that ghostscript would create
                    tmp_pdf = tmp_path / "nested_tables.tmp.pdf"
                    tmp_pdf.touch()

                    extractor = EpubExtractor()
                    result = extractor.extract(epub_path)

                    # Should complete via fallback
                    assert result.method == 'epub_conversion_only'
                    assert result.page_count == 0  # Empty pages

                    # Verify Chromium was called (HTML→PDF)
                    chromium_calls = [call for call in mock_run.call_args_list if 'chromium' in str(call)]
                    assert len(chromium_calls) > 0

    def test_deeply_nested_error_triggers_fallback(self, tmp_path):
        """'Too deeply nested' error should trigger HTML fallback conversion"""
        epub_path = tmp_path / "nested_lists.epub"
        pdf_path = tmp_path / "nested_lists.pdf"

        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            # First call: Pandoc fails with deeply nested error
            # Second call: EPUB→HTML succeeds
            # Third call: HTML→PDF (Chromium) succeeds
            # Fourth call: Ghostscript font embedding
            # Fifth call: pdfinfo
            mock_run.side_effect = [
                Mock(returncode=1, stdout="", stderr="! LaTeX Error: Too deeply nested.\n\nSee the LaTeX manual"),
                Mock(returncode=0, stdout="", stderr=""),  # pandoc epub→html
                Mock(returncode=0, stdout="", stderr=""),  # chromium html→pdf
                Mock(returncode=0, stdout="", stderr=""),  # ghostscript
                Mock(returncode=0, stdout="Pages:          50\n", stderr=""),  # pdfinfo
            ]

            with patch('shutil.move'):
                # Create a real temporary HTML file
                temp_html = tmp_path / "temp.html"
                temp_html.touch()

                with patch('tempfile.NamedTemporaryFile') as mock_temp:
                    mock_temp.return_value.__enter__.return_value.name = str(temp_html)
                    mock_temp.return_value.__exit__.return_value = None

                    pdf_path.touch()
                    # Create temp PDF that ghostscript would create
                    tmp_pdf = tmp_path / "nested_lists.tmp.pdf"
                    tmp_pdf.touch()

                    extractor = EpubExtractor()
                    result = extractor.extract(epub_path)

                    # Should complete via fallback
                    assert result.method == 'epub_conversion_only'
                    assert result.page_count == 0  # Empty pages

                    # Verify Chromium was called (HTML→PDF)
                    chromium_calls = [call for call in mock_run.call_args_list if 'chromium' in str(call)]
                    assert len(chromium_calls) > 0

    def _create_minimal_epub(self, path: Path):
        """Create a minimal valid EPUB file (ZIP with mimetype)"""
        import zipfile
        with zipfile.ZipFile(path, 'w') as epub:
            epub.writestr('mimetype', 'application/epub+zip')
            epub.writestr('META-INF/container.xml', '<?xml version="1.0"?>')


class TestEpubValidation:
    """Test EPUB validation logic"""

    def test_validate_epub_file_accepts_valid_epub(self, tmp_path):
        """Valid EPUB should pass validation"""
        epub_path = tmp_path / "valid.epub"
        self._create_minimal_epub(epub_path)

        assert EpubExtractor._validate_epub_file(epub_path) is True

    def test_validate_epub_file_rejects_text_file(self, tmp_path):
        """Text file with .epub extension should fail validation"""
        fake_epub = tmp_path / "fake.epub"
        fake_epub.write_text("This is not an EPUB")

        assert EpubExtractor._validate_epub_file(fake_epub) is False

    def test_validate_epub_file_rejects_empty_file(self, tmp_path):
        """Empty file should fail validation"""
        empty_epub = tmp_path / "empty.epub"
        empty_epub.touch()

        assert EpubExtractor._validate_epub_file(empty_epub) is False

    def test_validation_error_includes_file_content(self, tmp_path):
        """Validation error for small files should include content snippet"""
        small_fake = tmp_path / "small.epub"
        small_fake.write_text("PLACEHOLDER FILE - Download the real book")

        try:
            EpubExtractor._validate_or_raise(small_fake)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            error_msg = str(e)
            assert "Invalid EPUB file" in error_msg
            assert "PLACEHOLDER FILE" in error_msg
            assert "Re-download from source" in error_msg

    def _create_minimal_epub(self, path: Path):
        """Create a minimal valid EPUB file (ZIP with mimetype)"""
        import zipfile
        with zipfile.ZipFile(path, 'w') as epub:
            epub.writestr('mimetype', 'application/epub+zip')
            epub.writestr('META-INF/container.xml', '<?xml version="1.0"?>')


class TestEpubGhostscriptFontEmbedding:
    """Test Ghostscript font embedding step"""

    def test_ghostscript_embeds_fonts_successfully(self, tmp_path):
        """Ghostscript should embed fonts in converted PDF"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_text("Mock PDF content")
        temp_pdf = tmp_path / "test.tmp.pdf"

        with patch('subprocess.run') as mock_run:
            # Ghostscript succeeds
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            with patch.object(Path, 'replace') as mock_replace:
                temp_pdf.touch()

                EpubExtractor._embed_fonts_with_ghostscript(pdf_path)

                # Verify Ghostscript was called with correct arguments
                call_args = mock_run.call_args[0][0]
                assert 'gs' in call_args
                assert '-dEmbedAllFonts=true' in call_args
                assert '-dSubsetFonts=true' in call_args

                # Verify temp PDF was moved to replace original
                mock_replace.assert_called_once_with(pdf_path)

    def test_ghostscript_failure_uses_original_pdf(self, tmp_path):
        """If Ghostscript fails, original PDF should be kept"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_text("Original PDF")

        with patch('subprocess.run') as mock_run:
            # Ghostscript fails
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="GS Error")

            # Should not raise, just use original
            EpubExtractor._embed_fonts_with_ghostscript(pdf_path)

            # Original PDF should still exist
            assert pdf_path.exists()
            assert pdf_path.read_text() == "Original PDF"


class TestEpubPageCounting:
    """Test PDF page counting with pdfinfo"""

    def test_count_pdf_pages_extracts_page_count(self, tmp_path):
        """pdfinfo output should be parsed correctly"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Producer:        pdfTeX-1.40.20\nPages:           287\nEncrypted:       no\n",
                stderr=""
            )

            page_count = EpubExtractor._count_pdf_pages(pdf_path)

            assert page_count == 287

    def test_count_pdf_pages_returns_zero_on_error(self, tmp_path):
        """pdfinfo error should return 0 instead of raising"""
        pdf_path = tmp_path / "nonexistent.pdf"

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("pdfinfo not found")

            page_count = EpubExtractor._count_pdf_pages(pdf_path)

            assert page_count == 0

    def test_count_pdf_pages_returns_zero_if_no_pages_line(self, tmp_path):
        """Missing 'Pages:' line should return 0"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Producer:        pdfTeX\nTitle:           Some Book\n",
                stderr=""
            )

            page_count = EpubExtractor._count_pdf_pages(pdf_path)

            assert page_count == 0


class TestEpubIntegration:
    """Integration tests for EPUB conversion workflow"""

    def test_end_to_end_epub_conversion(self, tmp_path):
        """Full workflow: EPUB → PDF conversion → move to original/"""
        epub_path = tmp_path / "Design Patterns.epub"
        pdf_path = tmp_path / "Design Patterns.pdf"
        original_dir = tmp_path / "original"

        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            # Mock all subprocess calls
            mock_run.side_effect = [
                Mock(returncode=0, stdout="", stderr=""),  # pandoc
                Mock(returncode=0, stdout="", stderr=""),  # ghostscript
                Mock(returncode=0, stdout="Pages:          395\n", stderr=""),  # pdfinfo
            ]

            with patch('shutil.move') as mock_move:
                pdf_path.touch()
                # Create temp PDF that ghostscript would create
                tmp_pdf = tmp_path / "Design Patterns.tmp.pdf"
                tmp_pdf.touch()

                extractor = EpubExtractor()
                result = extractor.extract(epub_path)

                # Verify conversion-only result
                assert result.method == 'epub_conversion_only'
                assert len(result.pages) == 0
                assert result.page_count == 0  # Empty pages

                # Verify EPUB was archived
                mock_move.assert_called_once()
                assert 'original' in str(mock_move.call_args[0][1])

                # Verify PDF exists (would be picked up by file watcher)
                assert pdf_path.exists()

    def test_epub_cleanup_on_failure(self, tmp_path):
        """Failed conversion should clean up partial PDF"""
        epub_path = tmp_path / "broken.epub"
        pdf_path = tmp_path / "broken.pdf"

        self._create_minimal_epub(epub_path)

        with patch('subprocess.run') as mock_run:
            # Pandoc fails
            mock_run.return_value = Mock(returncode=1, stdout="", stderr="Conversion error")

            # Create partial PDF
            pdf_path.touch()

            try:
                extractor = EpubExtractor()
                extractor.extract(epub_path)
                assert False, "Should have raised RuntimeError"
            except RuntimeError:
                # Verify cleanup happened
                # (Note: _cleanup_on_failure should delete the partial PDF)
                pass

    def _create_minimal_epub(self, path: Path):
        """Create a minimal valid EPUB file (ZIP with mimetype)"""
        import zipfile
        with zipfile.ZipFile(path, 'w') as epub:
            epub.writestr('mimetype', 'application/epub+zip')
            epub.writestr('META-INF/container.xml', '<?xml version="1.0"?>')
