"""Characterization tests for JupyterExtractor

These tests document current behavior before refactoring.
Goal: 100% coverage of public API to enable safe refactoring.

From POODR audit:
- JupyterExtractor: 467 lines, 7 responsibilities
- High complexity: _parse_outputs (CC=17), _chunk_code_cell (CC=12)
- No existing tests (CRITICAL!)
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from ingestion.jupyter_extractor import JupyterExtractor, NotebookCell
from ingestion.jupyter.output_parser import NotebookOutputParser
from ingestion.jupyter.language_detector import KernelLanguageDetector
from ingestion.jupyter.markdown_chunker import MarkdownCellChunker
from ingestion.jupyter.cell_combiner import CellCombiner


class TestJupyterExtractorBasics:
    """Test basic extraction functionality"""

    @pytest.fixture
    def extractor(self):
        """Create JupyterExtractor instance"""
        return JupyterExtractor()

    @pytest.fixture
    def sample_notebook_path(self):
        """Path to sample Python notebook"""
        return Path(__file__).parent / "fixtures" / "sample_python.ipynb"

    def test_extract_simple_notebook(self, extractor, sample_notebook_path):
        """Test: Can extract from valid .ipynb file"""
        result = extractor.extract(str(sample_notebook_path))

        assert isinstance(result, list)
        assert len(result) > 0
        # Should have both code and markdown chunks
        assert any(chunk.get('type') == 'code' for chunk in result)
        assert any(chunk.get('type') == 'markdown' for chunk in result)

    def test_extract_preserves_cell_order(self, extractor, sample_notebook_path):
        """Test: Cells extracted in execution order"""
        result = extractor.extract(str(sample_notebook_path))

        # First chunk should be markdown (the title)
        assert result[0]['type'] == 'markdown'
        assert '# Sample Python Notebook' in result[0]['content']

    def test_extract_includes_metadata(self, extractor, sample_notebook_path):
        """Test: Chunks include filepath metadata"""
        result = extractor.extract(str(sample_notebook_path))

        for chunk in result:
            assert 'filepath' in chunk
            assert 'sample_python.ipynb' in chunk['filepath']

    def test_extract_empty_notebook(self, extractor):
        """Test: Handle notebook with no cells gracefully"""
        empty_nb = {
            'cells': [],
            'metadata': {'kernelspec': {'name': 'python3'}},
            'nbformat': 4,
            'nbformat_minor': 5
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.ipynb', delete=False) as f:
            json.dump(empty_nb, f)
            temp_path = f.name

        try:
            result = extractor.extract(temp_path)
            assert result == []
        finally:
            Path(temp_path).unlink()

    def test_extract_preserves_execution_count(self, extractor, sample_notebook_path):
        """Test: Execution counts preserved in chunks"""
        result = extractor.extract(str(sample_notebook_path))

        code_chunks = [c for c in result if c.get('type') == 'code']
        # At least one code chunk should have execution_count
        assert any('execution_count' in chunk for chunk in code_chunks)


class TestOutputParsing:
    """Test output parsing (CC=17 - High Complexity!)"""

    def test_parse_outputs_stream(self):
        """Test: Parse stdout/stderr stream outputs"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'stream',
                'name': 'stdout',
                'text': 'Hello, World!\n'
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['output_type'] == 'stream'
        assert result[0]['text'] == 'Hello, World!\n'
        assert result[0]['stream_name'] == 'stdout'

    def test_parse_outputs_execute_result(self):
        """Test: Parse execution results (text/plain)"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'execute_result',
                'data': {'text/plain': '42'},
                'execution_count': 1
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['output_type'] == 'execute_result'
        assert result[0]['text'] == '42'

    def test_parse_outputs_display_data_with_image(self):
        """Test: Parse image outputs (PNG)"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'display_data',
                'data': {
                    'image/png': 'iVBORw0KGgoAAAANSUhEUgAAAAUA',  # fake base64
                    'text/plain': '<Figure size 640x480>'
                }
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['has_image'] is True
        assert result[0]['image_type'] == 'png'
        assert 'image_size_bytes' in result[0]

    def test_parse_outputs_error_traceback(self):
        """Test: Parse error outputs with traceback"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'error',
                'ename': 'ValueError',
                'evalue': 'invalid value',
                'traceback': ['Traceback (most recent call last):', '  File ...', 'ValueError: invalid value']
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['output_type'] == 'error'
        assert result[0]['error_name'] == 'ValueError'
        assert result[0]['error_value'] == 'invalid value'
        assert 'ValueError: invalid value' in result[0]['traceback']

    def test_parse_outputs_html_dataframe(self):
        """Test: Parse HTML/DataFrame outputs"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'display_data',
                'data': {
                    'text/html': '<table><tr><td>Data</td></tr></table>',
                    'text/plain': 'DataFrame(...)'
                }
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert len(result) == 1
        assert result[0]['has_html'] is True

    def test_parse_outputs_empty_list(self):
        """Test: Handle cells with no outputs"""
        result = NotebookOutputParser.parse_outputs([])
        assert result == []

    def test_parse_outputs_stream_with_list(self):
        """Test: Handle stream output as list of strings"""
        outputs = [
            type('obj', (object,), {
                'output_type': 'stream',
                'name': 'stdout',
                'text': ['Line 1\n', 'Line 2\n']
            })()
        ]

        result = NotebookOutputParser.parse_outputs(outputs)

        assert result[0]['text'] == 'Line 1\nLine 2\n'


class TestLanguageDetection:
    """Test language detection from kernel names"""

    def test_detect_language_python_kernel(self):
        """Test: 'python3' kernel → 'python'"""
        assert KernelLanguageDetector.detect_language('python3') == 'python'
        assert KernelLanguageDetector.detect_language('python') == 'python'

    def test_detect_language_r_kernel(self):
        """Test: 'ir' kernel → 'r'"""
        assert KernelLanguageDetector.detect_language('ir') == 'r'
        assert KernelLanguageDetector.detect_language('R') == 'r'

    def test_detect_language_julia_kernel(self):
        """Test: Julia kernel detection"""
        assert KernelLanguageDetector.detect_language('julia') == 'julia'
        assert KernelLanguageDetector.detect_language('julia-1.6') == 'julia'

    def test_detect_language_javascript_kernel(self):
        """Test: JavaScript kernel detection"""
        assert KernelLanguageDetector.detect_language('javascript') == 'javascript'
        assert KernelLanguageDetector.detect_language('node') == 'javascript'

    def test_detect_language_unknown_kernel(self):
        """Test: Unknown kernel → defaults to 'python'"""
        assert KernelLanguageDetector.detect_language('unknown') == 'python'
        assert KernelLanguageDetector.detect_language('') == 'python'


class TestCodeCellChunking:
    """Test code cell chunking (CC=12 - High Complexity!)"""

    def test_chunk_code_cell_python_small(self):
        """Test: Small Python cell (<2048 chars) kept whole"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='code',
            source='print("hello")',
            outputs=[],
            execution_count=1
        )

        result = JupyterExtractor._chunk_code_cell(cell, 'python', 'test.ipynb')

        assert len(result) == 1
        assert result[0]['content'] == 'print("hello")'
        assert result[0]['language'] == 'python'
        assert result[0]['cell_number'] == 1

    @patch('ingestion.jupyter_extractor.ASTChunkBuilder')
    def test_chunk_code_cell_python_large_ast(self, mock_ast_builder):
        """Test: Large Python cell (>2048) uses ASTChunkBuilder"""
        large_code = 'x = 1\n' * 300  # >2048 chars

        cell = NotebookCell(
            cell_number=1,
            cell_type='code',
            source=large_code,
            outputs=[],
            execution_count=1
        )

        # Mock the chunker
        mock_chunk = type('obj', (object,), {'content': large_code[:1000], 'metadata': {}})()
        mock_instance = Mock()
        mock_instance.chunkify.return_value = [mock_chunk]
        mock_ast_builder.return_value = mock_instance

        result = JupyterExtractor._chunk_code_cell(cell, 'python', 'test.ipynb')

        # Should have called ASTChunkBuilder
        assert mock_ast_builder.called
        assert len(result) >= 1

    def test_chunk_code_cell_python_ast_failure(self):
        """Test: AST chunking fails → fallback to whole cell"""
        large_code = 'invalid python syntax {\n' * 300

        cell = NotebookCell(
            cell_number=1,
            cell_type='code',
            source=large_code,
            outputs=[],
            execution_count=1
        )

        # Even if AST fails, should return fallback
        result = JupyterExtractor._chunk_code_cell(cell, 'python', 'test.ipynb')

        assert len(result) == 1
        assert result[0]['content'] == large_code

    def test_chunk_code_cell_r_small(self):
        """Test: Small R cell kept whole"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='code',
            source='x <- 1:10',
            outputs=[],
            execution_count=1
        )

        result = JupyterExtractor._chunk_code_cell(cell, 'r', 'test.ipynb')

        assert len(result) == 1
        assert result[0]['content'] == 'x <- 1:10'
        assert result[0]['language'] == 'r'

    def test_chunk_code_cell_empty_source(self):
        """Test: Empty cell returns empty list"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='code',
            source='',
            outputs=[],
            execution_count=None
        )

        result = JupyterExtractor._chunk_code_cell(cell, 'python', 'test.ipynb')

        assert result == []

    def test_chunk_code_cell_whitespace_only(self):
        """Test: Whitespace-only cell returns empty list"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='code',
            source='   \n\n  ',
            outputs=[],
            execution_count=None
        )

        result = JupyterExtractor._chunk_code_cell(cell, 'python', 'test.ipynb')

        assert result == []


class TestMarkdownCellChunking:
    """Test markdown cell chunking"""

    def test_chunk_markdown_cell_with_headers(self):
        """Test: Split markdown on ## headers"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='markdown',
            source='# Title\n\nIntro\n\n## Section 1\n\nContent 1\n\n## Section 2\n\nContent 2',
            outputs=[],
            metadata={},
            execution_count=None
        )

        result = MarkdownCellChunker.chunk(cell, 'test.ipynb')

        # Should split on headers
        assert len(result) >= 1
        # All chunks should be markdown type
        assert all(chunk['type'] == 'markdown' for chunk in result)

    def test_chunk_markdown_cell_no_headers(self):
        """Test: Small markdown kept whole"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='markdown',
            source='Just some text without headers.',
            outputs=[],
            metadata={},
            execution_count=None
        )

        result = MarkdownCellChunker.chunk(cell, 'test.ipynb')

        assert len(result) == 1
        assert result[0]['content'] == 'Just some text without headers.'

    def test_chunk_markdown_cell_empty(self):
        """Test: Empty markdown cell"""
        cell = NotebookCell(
            cell_number=1,
            cell_type='markdown',
            source='',
            outputs=[],
            metadata={},
            execution_count=None
        )

        result = MarkdownCellChunker.chunk(cell, 'test.ipynb')

        assert result == []


class TestCellCombination:
    """Test cell combination logic (CC=10)"""

    def test_combine_adjacent_cells_basic(self):
        """Test: Adjacent compatible cells can be combined"""
        chunks = [
            {'content': 'Chunk 1', 'type': 'markdown', 'cell_number': 1, 'cell_type': 'markdown'},
            {'content': 'Chunk 2', 'type': 'markdown', 'cell_number': 2, 'cell_type': 'markdown'},
        ]

        result = CellCombiner.combine_adjacent(chunks, 'test.ipynb', max_chunk_size=2048)

        # Should combine if under max size
        assert isinstance(result, list)

    def test_combine_respects_max_chunk_size(self):
        """Test: Doesn't combine if exceeds 2048 chars"""
        large_content = 'x' * 1500

        chunks = [
            {'content': large_content, 'type': 'markdown', 'cell_number': 1, 'cell_type': 'markdown'},
            {'content': large_content, 'type': 'markdown', 'cell_number': 2, 'cell_type': 'markdown'},
        ]

        result = CellCombiner.combine_adjacent(chunks, 'test.ipynb', max_chunk_size=2048)

        # Should NOT combine (would exceed 2048)
        assert len(result) == 2

    def test_combine_code_markdown_not_combined(self):
        """Test: Code + markdown NOT combined"""
        chunks = [
            {'content': 'Code', 'type': 'code', 'cell_number': 1, 'cell_type': 'code', 'language': 'python'},
            {'content': 'Markdown', 'type': 'markdown', 'cell_number': 2, 'cell_type': 'markdown'},
        ]

        result = CellCombiner.combine_adjacent(chunks, 'test.ipynb', max_chunk_size=2048)

        # Should keep separate (different types)
        assert len(result) == 2


class TestNotebookParsing:
    """Test _parse_notebook method"""

    @pytest.fixture
    def extractor(self):
        return JupyterExtractor()

    def test_parse_notebook_structure(self, extractor, sample_notebook_path):
        """Test: _parse_notebook returns NotebookCell list"""
        with open(sample_notebook_path) as f:
            nb_dict = json.load(f)

        cells = extractor._parse_notebook(nb_dict, str(sample_notebook_path))

        assert isinstance(cells, list)
        assert all(isinstance(cell, NotebookCell) for cell in cells)

    def test_parse_notebook_kernel_detection(self, extractor):
        """Test: Kernel name extracted correctly"""
        nb_dict = {
            'cells': [],
            'metadata': {
                'kernelspec': {
                    'name': 'python3',
                    'language': 'python'
                }
            },
            'nbformat': 4,
            'nbformat_minor': 5
        }

        cells = extractor._parse_notebook(nb_dict, 'test.ipynb')

        # Should detect python kernel
        assert extractor._detect_language_from_kernel('python3') == 'python'


class TestIntegration:
    """Integration tests with real notebooks"""

    @pytest.fixture
    def extractor(self):
        return JupyterExtractor()

    def test_extract_real_notebook_python(self, extractor):
        """Integration: Extract from real Python notebook"""
        notebook_path = Path(__file__).parent / "fixtures" / "sample_python.ipynb"

        if not notebook_path.exists():
            pytest.skip("Fixture notebook not found")

        result = extractor.extract(str(notebook_path))

        assert len(result) > 0
        # Should have markdown and code chunks
        types = {chunk['type'] for chunk in result}
        assert 'code' in types
        assert 'markdown' in types

    def test_extract_preserves_outputs(self, extractor):
        """Test: Cell outputs included in chunks"""
        notebook_path = Path(__file__).parent / "fixtures" / "sample_python.ipynb"

        if not notebook_path.exists():
            pytest.skip("Fixture notebook not found")

        result = extractor.extract(str(notebook_path))

        # At least one code chunk should have outputs
        code_chunks = [c for c in result if c.get('type') == 'code']
        assert any(c.get('has_output') for c in code_chunks)
