"""
Jupyter Notebook extraction using Docling HybridChunker.

Processing strategy:
1. Parse .ipynb file with nbformat
2. Convert all cells to markdown (code cells wrapped in fenced blocks)
3. Apply HybridChunker for semantic, token-aware chunking
4. Return chunks with notebook metadata

This approach treats notebooks as unified documents rather than
fragmenting by cell boundaries, resulting in better chunk coherence.
"""

from pathlib import Path
from typing import ClassVar, List, Set, Tuple
import tempfile
import os

from domain_models import ExtractionResult
from pipeline.interfaces import ExtractorInterface


class JupyterExtractor(ExtractorInterface):
    """Extract and chunk Jupyter notebooks using HybridChunker

    Converts notebook to markdown, then applies Docling's HybridChunker
    for semantic chunking that respects document structure.
    """

    SUPPORTED_EXTENSIONS: ClassVar[Set[str]] = {'.ipynb'}

    @property
    def name(self) -> str:
        return "jupyter"

    def extract(self, path: Path) -> ExtractionResult:
        """Extract and chunk Jupyter notebook

        Args:
            path: Path to .ipynb file

        Returns:
            ExtractionResult with chunked pages
        """
        nb_metadata, markdown_content = self._notebook_to_markdown(path)
        language = nb_metadata.get('language', 'python')

        chunks = self._chunk_with_hybrid(markdown_content)

        if not chunks:
            # Fallback: return whole content as single chunk
            chunks = [markdown_content] if markdown_content.strip() else []

        pages = [(chunk, i) for i, chunk in enumerate(chunks)]
        return ExtractionResult(pages=pages, method=f'jupyter_{language}')

    def _notebook_to_markdown(self, path: Path) -> Tuple[dict, str]:
        """Convert notebook to markdown string

        Args:
            path: Path to notebook

        Returns:
            Tuple of (metadata dict, markdown content)
        """
        nbformat = self._import_nbformat()

        with open(path, 'r', encoding='utf-8') as f:
            notebook = nbformat.read(f, as_version=nbformat.NO_CONVERT)

        metadata = {
            'kernel': notebook.metadata.get('kernelspec', {}).get('name', 'unknown'),
            'language': notebook.metadata.get('kernelspec', {}).get('language', 'python'),
        }

        language = metadata['language']
        md_parts = []

        for cell in notebook.cells:
            source = cell.source if isinstance(cell.source, str) else ''.join(cell.source)
            if not source.strip():
                continue

            if cell.cell_type == 'markdown':
                md_parts.append(source)
            elif cell.cell_type == 'code':
                md_parts.append(f'```{language}')
                md_parts.append(source)
                md_parts.append('```')

        return metadata, '\n\n'.join(md_parts)

    def _chunk_with_hybrid(self, markdown_content: str) -> List[str]:
        """Apply HybridChunker to markdown content

        Args:
            markdown_content: Markdown string to chunk

        Returns:
            List of chunk strings
        """
        if not markdown_content.strip():
            return []

        try:
            from ingestion.extractors.docling_extractor import DoclingExtractor
            from config import default_config

            # Write to temp file for Docling conversion
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.md', delete=False, encoding='utf-8'
            ) as f:
                f.write(markdown_content)
                temp_path = f.name

            try:
                converter = DoclingExtractor.get_converter()
                result = converter.convert(temp_path)
                document = result.document

                chunker = DoclingExtractor.get_chunker(default_config.chunks.max_tokens)
                chunks = []

                for chunk in chunker.chunk(document):
                    chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                    if chunk_text.strip():
                        chunks.append(chunk_text)

                return chunks
            finally:
                os.unlink(temp_path)

        except Exception:
            return []

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
