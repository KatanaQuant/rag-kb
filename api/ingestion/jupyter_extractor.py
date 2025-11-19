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
    """Extracts and chunks Jupyter notebooks (.ipynb) with AST-aware code processing

    Features:
    - AST-based chunking for Python (via astchunk) and R (via tree-sitter)
    - Smart cell combining (adjacent same-type cells)
    - Markdown header boundaries separate chunks
    - Image/output preservation as metadata
    - Cell execution context preservation
    """

    @staticmethod
    def _parse_notebook(path: Path) -> Tuple[Dict, List[NotebookCell]]:
        """Parse notebook file into cells

        Args:
            path: Path to .ipynb file

        Returns:
            Tuple of (notebook_metadata, list of parsed cells)

        Raises:
            ImportError: If nbformat not available
            Exception: If notebook parsing fails
        """
        try:
            import nbformat
        except ImportError as e:
            raise ImportError(
                f"nbformat not available: {e}\n"
                "Install with: pip install nbformat>=5.9.0"
            )

        # Read notebook
        with open(path, 'r', encoding='utf-8') as f:
            notebook = nbformat.read(f, as_version=nbformat.NO_CONVERT)

        # Extract notebook-level metadata
        nb_metadata = {
            'kernel': notebook.metadata.get('kernelspec', {}).get('name', 'unknown'),
            'language': notebook.metadata.get('kernelspec', {}).get('language', 'unknown'),
            'nbformat': notebook.nbformat,
            'nbformat_minor': notebook.nbformat_minor,
        }

        # Parse cells
        cells = []
        for i, cell in enumerate(notebook.cells):
            # Get cell source (might be list of strings)
            source = cell.source if isinstance(cell.source, str) else ''.join(cell.source)

            # Get outputs (only for code cells)
            outputs = []
            if cell.cell_type == 'code' and hasattr(cell, 'outputs'):
                outputs = JupyterExtractor._parse_outputs(cell.outputs)

            # Create parsed cell
            parsed_cell = NotebookCell(
                cell_type=cell.cell_type,
                source=source,
                cell_number=i,
                outputs=outputs,
                metadata=dict(cell.metadata) if hasattr(cell, 'metadata') else {},
                execution_count=cell.execution_count if hasattr(cell, 'execution_count') else None
            )
            cells.append(parsed_cell)

        return nb_metadata, cells

    @staticmethod
    def _parse_outputs(outputs: List) -> List[Dict]:
        """Parse cell outputs (text, images, errors)

        Args:
            outputs: List of notebook output objects

        Returns:
            List of parsed output dictionaries
        """
        parsed = []

        for output in outputs:
            output_dict = {'output_type': output.output_type}

            if output.output_type == 'stream':
                # stdout/stderr text
                text = output.text if isinstance(output.text, str) else ''.join(output.text)
                output_dict['text'] = text
                output_dict['stream_name'] = output.name

            elif output.output_type == 'execute_result' or output.output_type == 'display_data':
                # Execution results or display outputs
                data = output.data if hasattr(output, 'data') else {}

                # Text output
                if 'text/plain' in data:
                    text = data['text/plain']
                    output_dict['text'] = text if isinstance(text, str) else ''.join(text)

                # Image output (preserve as metadata)
                if 'image/png' in data:
                    output_dict['has_image'] = True
                    output_dict['image_type'] = 'png'
                    # Don't include base64 data - too large. Just note it exists.
                    output_dict['image_size_bytes'] = len(data['image/png'])

                if 'image/jpeg' in data:
                    output_dict['has_image'] = True
                    output_dict['image_type'] = 'jpeg'
                    output_dict['image_size_bytes'] = len(data['image/jpeg'])

                # HTML/DataFrame output
                if 'text/html' in data:
                    output_dict['has_html'] = True

            elif output.output_type == 'error':
                # Error traceback
                traceback = output.traceback if hasattr(output, 'traceback') else []
                output_dict['error_name'] = output.ename if hasattr(output, 'ename') else 'Error'
                output_dict['error_value'] = output.evalue if hasattr(output, 'evalue') else ''
                output_dict['traceback'] = '\n'.join(traceback) if traceback else ''

            parsed.append(output_dict)

        return parsed

    @staticmethod
    def _detect_language_from_kernel(kernel_name: str) -> str:
        """Detect programming language from kernel name

        Args:
            kernel_name: Jupyter kernel name (e.g., 'python3', 'ir', 'julia-1.6')

        Returns:
            Language name for code chunking
        """
        kernel_lower = kernel_name.lower()

        if 'python' in kernel_lower:
            return 'python'
        elif kernel_lower in ('ir', 'r'):  # IR is the R kernel
            return 'r'
        elif 'julia' in kernel_lower:
            return 'julia'
        elif 'javascript' in kernel_lower or 'node' in kernel_lower:
            return 'javascript'
        else:
            # Unknown kernel, default to python
            return 'python'

    @staticmethod
    def _chunk_code_cell(cell: NotebookCell, language: str, filepath: str) -> List[Dict]:
        """Chunk code cell - cell-level chunking with optional AST splitting for large cells

        Strategy:
        - Each cell is a natural execution unit
        - For large Python cells (>2048 chars): use astchunk (fast, well-tested)
        - For large R cells (>2048 chars): use TreeSitterChunker (AST-based)
        - Small cells: keep whole cell (preserves execution semantics)

        Args:
            cell: Notebook cell to chunk
            language: Programming language ('python', 'r', etc.)
            filepath: Notebook filepath for metadata

        Returns:
            List of code chunks with metadata
        """
        if not cell.source or not cell.source.strip():
            return []

        chunks = []
        cell_size = len(cell.source)

        # Python: use astchunk if cell is large, otherwise keep whole cell
        if language == 'python' and cell_size > 2048:
            try:
                from astchunk import ASTChunkBuilder
                chunker = ASTChunkBuilder(
                    max_chunk_size=2048,
                    language='python',
                    metadata_template='default'
                )
                code_chunks = chunker.chunkify(cell.source)

                # Convert astchunk format to our format
                for chunk in code_chunks:
                    chunks.append({
                        'content': chunk.content,
                        'type': 'code',
                        'language': language,
                        'cell_number': cell.cell_number,
                        'cell_type': 'code',
                        'execution_count': cell.execution_count,
                        'has_output': len(cell.outputs) > 0,
                        'outputs': cell.outputs,
                        'metadata': chunk.metadata if hasattr(chunk, 'metadata') else {},
                        'filepath': filepath,
                    })

            except Exception as e:
                # Fallback: treat entire cell as one chunk
                print(f"Warning: AST chunking failed for Python cell {cell.cell_number}: {e}")
                chunks.append({
                    'content': cell.source,
                    'type': 'code',
                    'language': language,
                    'cell_number': cell.cell_number,
                    'cell_type': 'code',
                    'execution_count': cell.execution_count,
                    'has_output': len(cell.outputs) > 0,
                    'outputs': cell.outputs,
                    'metadata': {'note': 'AST chunking failed, using full cell'},
                    'filepath': filepath,
                })

        # R: use TreeSitterChunker if cell is large
        elif language == 'r' and cell_size > 2048:
            try:
                from ingestion.tree_sitter_chunker import TreeSitterChunker
                chunker = TreeSitterChunker(
                    language='r',
                    max_chunk_size=2048,
                    metadata_template='default'
                )
                code_chunks = chunker.chunkify(cell.source, filepath=filepath)

                # Convert TreeSitterChunker format to our format
                for chunk in code_chunks:
                    chunks.append({
                        'content': chunk['content'],
                        'type': 'code',
                        'language': language,
                        'cell_number': cell.cell_number,
                        'cell_type': 'code',
                        'execution_count': cell.execution_count,
                        'has_output': len(cell.outputs) > 0,
                        'outputs': cell.outputs,
                        'metadata': chunk.get('metadata', {}),
                        'filepath': filepath,
                    })

            except Exception as e:
                # Fallback: treat entire cell as one chunk
                print(f"Warning: AST chunking failed for R cell {cell.cell_number}: {e}")
                chunks.append({
                    'content': cell.source,
                    'type': 'code',
                    'language': language,
                    'cell_number': cell.cell_number,
                    'cell_type': 'code',
                    'execution_count': cell.execution_count,
                    'has_output': len(cell.outputs) > 0,
                    'outputs': cell.outputs,
                    'metadata': {'note': 'AST chunking failed, using full cell'},
                    'filepath': filepath,
                })

        # All other cases: keep cell as one chunk (best for execution semantics)
        else:
            chunks.append({
                'content': cell.source,
                'type': 'code',
                'language': language,
                'cell_number': cell.cell_number,
                'cell_type': 'code',
                'execution_count': cell.execution_count,
                'has_output': len(cell.outputs) > 0,
                'outputs': cell.outputs,
                'metadata': {'chunking': 'cell_level'},
                'filepath': filepath,
            })

        return chunks

    @staticmethod
    def _chunk_markdown_cell(cell: NotebookCell, filepath: str) -> List[Dict]:
        """Process markdown cell

        Markdown cells are usually section headers or explanations.
        Split on headers (## ) as natural boundaries.

        Args:
            cell: Notebook cell
            filepath: Notebook filepath

        Returns:
            List of markdown chunks
        """
        if not cell.source or not cell.source.strip():
            return []

        # Check if cell starts with header
        has_header = cell.source.strip().startswith('#')

        # For now, treat each markdown cell as one chunk
        # (Can enhance later to split on headers within cell)
        return [{
            'content': cell.source,
            'type': 'markdown',
            'cell_number': cell.cell_number,
            'cell_type': 'markdown',
            'is_header': has_header,
            'filepath': filepath,
        }]

    @staticmethod
    def _combine_adjacent_cells(chunks: List[Dict], max_combined_size: int = 2048) -> List[Dict]:
        """Smart combination of adjacent cells

        Strategy:
        - Markdown headers (##) create hard boundaries
        - Adjacent code cells can be combined if under size limit
        - Adjacent non-header markdown can be combined
        - Preserve cell number ranges

        Args:
            chunks: List of chunk dictionaries
            max_combined_size: Maximum size after combination

        Returns:
            List of combined chunks
        """
        if not chunks:
            return []

        combined = []
        current_group = [chunks[0]]
        current_size = len(chunks[0]['content'])

        for chunk in chunks[1:]:
            chunk_size = len(chunk['content'])

            # Check if we should start a new group
            should_split = False

            # Hard boundary: markdown header
            if chunk.get('type') == 'markdown' and chunk.get('is_header'):
                should_split = True

            # Type change boundary (code <-> markdown)
            elif chunk.get('type') != current_group[0].get('type'):
                should_split = True

            # Size limit reached
            elif current_size + chunk_size > max_combined_size:
                should_split = True

            if should_split:
                # Finalize current group
                if current_group:
                    combined.append(JupyterExtractor._merge_chunk_group(current_group))
                current_group = [chunk]
                current_size = chunk_size
            else:
                # Add to current group
                current_group.append(chunk)
                current_size += chunk_size

        # Add last group
        if current_group:
            combined.append(JupyterExtractor._merge_chunk_group(current_group))

        return combined

    @staticmethod
    def _merge_chunk_group(chunks: List[Dict]) -> Dict:
        """Merge multiple chunks into one

        Args:
            chunks: Chunks to merge (should be adjacent cells)

        Returns:
            Single merged chunk
        """
        if len(chunks) == 1:
            return chunks[0]

        # Combine content
        combined_content = '\n\n'.join(c['content'] for c in chunks)

        # Merge metadata
        cell_numbers = [c['cell_number'] for c in chunks]
        chunk_types = [c.get('type', 'unknown') for c in chunks]

        merged = {
            'content': combined_content,
            'type': chunks[0]['type'],  # Take first chunk's type
            'cell_numbers': cell_numbers,
            'cell_number_range': f"{min(cell_numbers)}-{max(cell_numbers)}",
            'combined_cells': len(chunks),
            'chunk_types': list(set(chunk_types)),
            'filepath': chunks[0].get('filepath', ''),
        }

        # If all chunks are code, preserve code metadata
        if all(c.get('type') == 'code' for c in chunks):
            merged['language'] = chunks[0].get('language', 'unknown')
            merged['cell_type'] = 'code'
            # Combine outputs from all cells
            all_outputs = []
            for c in chunks:
                all_outputs.extend(c.get('outputs', []))
            merged['outputs'] = all_outputs
            merged['has_output'] = len(all_outputs) > 0

        return merged

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract and chunk Jupyter notebook

        Main entry point. Processes notebook cells with AST-aware chunking
        and smart cell combining.

        Args:
            path: Path to .ipynb file

        Returns:
            ExtractionResult with notebook chunks as pages

        Raises:
            ImportError: If nbformat not available
            Exception: If notebook processing fails
        """
        # Parse notebook
        nb_metadata, cells = JupyterExtractor._parse_notebook(path)

        # Detect language from kernel
        language = JupyterExtractor._detect_language_from_kernel(nb_metadata['kernel'])

        # Process each cell
        all_chunks = []
        for cell in cells:
            if cell.cell_type == 'code':
                chunks = JupyterExtractor._chunk_code_cell(cell, language, str(path))
                all_chunks.extend(chunks)
            elif cell.cell_type == 'markdown':
                chunks = JupyterExtractor._chunk_markdown_cell(cell, str(path))
                all_chunks.extend(chunks)
            # Skip raw cells

        # Smart combination of adjacent cells
        combined_chunks = JupyterExtractor._combine_adjacent_cells(all_chunks)

        # Convert to ExtractionResult format (pages as (text, page_num) tuples)
        pages = []
        for i, chunk in enumerate(combined_chunks):
            # Format page text with metadata header
            page_text = f"[Jupyter Notebook Chunk {i+1}]\n"
            page_text += f"Cells: {chunk.get('cell_number_range', chunk.get('cell_number', 'unknown'))}\n"
            page_text += f"Type: {chunk.get('type', 'unknown')}\n"

            if chunk.get('type') == 'code':
                page_text += f"Language: {chunk.get('language', 'unknown')}\n"
                if chunk.get('has_output'):
                    page_text += f"Has Output: Yes ({len(chunk.get('outputs', []))} outputs)\n"

            page_text += "\n" + chunk['content']

            # Add as (text, page_num) tuple - use chunk index as page number
            pages.append((page_text, i))

        return ExtractionResult(
            pages=pages,
            method=f'jupyter_{language}'
        )
