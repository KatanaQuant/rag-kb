"""
Jupyter Notebook extraction with AST-aware code chunking and semantic cell combining.

Processing strategy:
1. Parse .ipynb file with nbformat
2. Separate cells by type (code, markdown, raw)
3. Code cells → AST-based chunking (R via tree-sitter, Python via astchunk)
4. Markdown cells → Content extraction with headers as boundaries
5. Smart combining: Group adjacent cells of same type, split at markdown headers
6. Preserve outputs: Text outputs, image metadata, errors
7. Enrich with cell metadata: cell numbers, kernel type, execution state
"""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import re

from domain_models import ExtractionResult

@dataclass
class NotebookCell:
    """Represents a parsed notebook cell"""
    cell_type: str  # 'code', 'markdown', 'raw'
    source: str
    cell_number: int
    outputs: List[Dict]
    metadata: Dict
    execution_count: Optional[int] = None

class JupyterExtractor:
    

    def __init__(self, chunker_factory=None):
        
        from ingestion.chunker_factory import ChunkerFactory
        self.chunker_factory = chunker_factory or ChunkerFactory()

    @staticmethod
    def _parse_notebook(path: Path) -> Tuple[Dict, List[NotebookCell]]:
        """Parse notebook file into cells"""
        nbformat = JupyterExtractor._import_nbformat()
        notebook = JupyterExtractor._read_notebook_file(path, nbformat)

        nb_metadata = JupyterExtractor._extract_notebook_metadata(notebook)
        cells = JupyterExtractor._parse_notebook_cells(notebook)

        return nb_metadata, cells

    @staticmethod
    def _import_nbformat():
        """Import nbformat with helpful error message"""
        try:
            import nbformat
            return nbformat
        except ImportError as e:
            raise ImportError(
                f"nbformat not available: {e}\n"
                "Install with: pip install nbformat>=5.9.0"
            )

    @staticmethod
    def _read_notebook_file(path: Path, nbformat):
        """Read notebook file using nbformat"""
        with open(path, 'r', encoding='utf-8') as f:
            return nbformat.read(f, as_version=nbformat.NO_CONVERT)

    @staticmethod
    def _extract_notebook_metadata(notebook) -> Dict:
        """Extract notebook-level metadata"""
        return {
            'kernel': notebook.metadata.get('kernelspec', {}).get('name', 'unknown'),
            'language': notebook.metadata.get('kernelspec', {}).get('language', 'unknown'),
            'nbformat': notebook.nbformat,
            'nbformat_minor': notebook.nbformat_minor,
        }

    @staticmethod
    def _parse_notebook_cells(notebook) -> List[NotebookCell]:
        """Parse all cells in notebook"""
        return [JupyterExtractor._parse_single_notebook_cell(cell, i)
                for i, cell in enumerate(notebook.cells)]

    @staticmethod
    def _parse_single_notebook_cell(cell, cell_number: int) -> NotebookCell:
        """Parse single notebook cell"""
        source = JupyterExtractor._get_cell_source(cell)
        outputs = JupyterExtractor._get_cell_outputs(cell)

        return NotebookCell(
            cell_type=cell.cell_type,
            source=source,
            cell_number=cell_number,
            outputs=outputs,
            metadata=dict(cell.metadata) if hasattr(cell, 'metadata') else {},
            execution_count=cell.execution_count if hasattr(cell, 'execution_count') else None
        )

    @staticmethod
    def _get_cell_source(cell) -> str:
        """Get cell source as string"""
        return cell.source if isinstance(cell.source, str) else ''.join(cell.source)

    @staticmethod
    def _get_cell_outputs(cell) -> list:
        """Get cell outputs if code cell"""
        if cell.cell_type != 'code' or not hasattr(cell, 'outputs'):
            return []

        from ingestion.jupyter.output_parser import NotebookOutputParser
        return NotebookOutputParser.parse_outputs(cell.outputs)

    def extract(self, path: Path) -> ExtractionResult:
        """Extract and chunk Jupyter notebook with AST-aware chunking"""
        nb_metadata, cells = JupyterExtractor._parse_notebook(path)
        language = self._detect_language(nb_metadata)

        all_chunks = self._process_cells(cells, language, path)
        combined_chunks = self._combine_adjacent_cells(all_chunks, path)
        pages = self._format_pages(combined_chunks)

        return ExtractionResult(pages=pages, method=f'jupyter_{language}')

    def _detect_language(self, nb_metadata: dict) -> str:
        """Detect programming language from kernel metadata"""
        from ingestion.jupyter.language_detector import KernelLanguageDetector
        return KernelLanguageDetector.detect_language(nb_metadata['kernel'])

    def _process_cells(self, cells: list, language: str, path: Path) -> list:
        """Process all notebook cells with appropriate chunkers"""
        chunkers = self._create_chunker_registry()
        all_chunks = []

        for cell in cells:
            chunks = self._process_single_cell(cell, chunkers, language, str(path))
            all_chunks.extend(chunks)

        return all_chunks

    def _create_chunker_registry(self) -> dict:
        """Create dictionary of cell type chunkers"""
        from ingestion.jupyter.code_cell_chunker import CodeCellChunker
        from ingestion.jupyter.markdown_chunker import MarkdownCellChunker

        return {
            'code': CodeCellChunker(self.chunker_factory),
            'markdown': MarkdownCellChunker(),
        }

    def _process_single_cell(self, cell, chunkers: dict, language: str, path: str) -> list:
        """Process single cell with appropriate chunker"""
        chunker = chunkers.get(cell.cell_type)
        if not chunker:
            return []

        if cell.cell_type == 'code':
            cell.language = language

        return chunker.chunk(cell, path)

    def _combine_adjacent_cells(self, chunks: list, path: Path) -> list:
        """Combine adjacent cells for better context"""
        from ingestion.jupyter.cell_combiner import CellCombiner
        return CellCombiner.combine_adjacent(chunks, str(path))

    def _format_pages(self, chunks: list) -> list:
        """Format chunks as pages with metadata headers"""
        return [(self._format_page_text(chunk, i), i) for i, chunk in enumerate(chunks)]

    def _format_page_text(self, chunk: dict, index: int) -> str:
        """Format single chunk as page text with metadata"""
        header = self._create_chunk_header(chunk, index)
        return header + "\n" + chunk['content']

    def _create_chunk_header(self, chunk: dict, index: int) -> str:
        """Create metadata header for chunk"""
        lines = [
            f"[Jupyter Notebook Chunk {index+1}]",
            f"Cells: {chunk.get('cell_number_range', chunk.get('cell_number', 'unknown'))}",
            f"Type: {chunk.get('type', 'unknown')}"
        ]

        if chunk.get('type') == 'code':
            lines.append(f"Language: {chunk.get('language', 'unknown')}")
            if chunk.get('has_output'):
                lines.append(f"Has Output: Yes ({len(chunk.get('outputs', []))} outputs)")

        return '\n'.join(lines)
