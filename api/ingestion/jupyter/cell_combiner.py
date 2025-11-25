

from typing import List, Dict

class CellCombiner:
    """Smart combination of adjacent notebook cells

    Single Responsibility: Combine adjacent cells

    Strategy:
    - Markdown headers (##) create hard boundaries
    - Adjacent code cells can be combined if under size limit
    - Adjacent non-header markdown can be combined
    - Preserve cell number ranges
    """

    @staticmethod
    def combine_adjacent(chunks: List[Dict], filepath: str, max_chunk_size: int = 2048) -> List[Dict]:
        """Smart combination of adjacent cells

        Strategy:
        - Markdown headers (##) create hard boundaries
        - Adjacent code cells can be combined if under size limit
        - Adjacent non-header markdown can be combined
        - Preserve cell number ranges

        Args:
            chunks: List of chunk dictionaries
            filepath: Notebook filepath for metadata
            max_chunk_size: Maximum size after combination

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
            should_split = CellCombiner._should_split_group(
                chunk, current_group[0], current_size, chunk_size, max_chunk_size
            )

            if should_split:
                combined.append(CellCombiner._merge_chunk_group(current_group))
                current_group = [chunk]
                current_size = chunk_size
            else:
                current_group.append(chunk)
                current_size += chunk_size

        if current_group:
            combined.append(CellCombiner._merge_chunk_group(current_group))

        return combined

    @staticmethod
    def _should_split_group(chunk: Dict, first_chunk: Dict, current_size: int,
                           chunk_size: int, max_chunk_size: int) -> bool:
        """Determine if chunk should start a new group"""
        if CellCombiner._is_header_boundary(chunk):
            return True
        if CellCombiner._is_type_change(chunk, first_chunk):
            return True
        if CellCombiner._exceeds_size_limit(current_size, chunk_size, max_chunk_size):
            return True
        return False

    @staticmethod
    def _is_header_boundary(chunk: Dict) -> bool:
        """Check if chunk is a markdown header (hard boundary)"""
        return chunk.get('type') == 'markdown' and chunk.get('is_header')

    @staticmethod
    def _is_type_change(chunk: Dict, first_chunk: Dict) -> bool:
        """Check if chunk type differs from group (code <-> markdown)"""
        return chunk.get('type') != first_chunk.get('type')

    @staticmethod
    def _exceeds_size_limit(current_size: int, chunk_size: int, max_chunk_size: int) -> bool:
        """Check if adding chunk would exceed size limit"""
        return current_size + chunk_size > max_chunk_size

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

        merged = CellCombiner._build_base_metadata(chunks)
        CellCombiner._add_code_metadata_if_applicable(chunks, merged)
        return merged

    @staticmethod
    def _build_base_metadata(chunks: List[Dict]) -> Dict:
        """Build base merged chunk metadata"""
        combined_content = '\n\n'.join(c['content'] for c in chunks)
        cell_numbers = [c['cell_number'] for c in chunks]
        chunk_types = [c.get('type', 'unknown') for c in chunks]

        return {
            'content': combined_content,
            'type': chunks[0]['type'],
            'cell_numbers': cell_numbers,
            'cell_number_range': f"{min(cell_numbers)}-{max(cell_numbers)}",
            'combined_cells': len(chunks),
            'chunk_types': list(set(chunk_types)),
            'filepath': chunks[0].get('filepath', ''),
        }

    @staticmethod
    def _add_code_metadata_if_applicable(chunks: List[Dict], merged: Dict):
        """Add code-specific metadata if all chunks are code cells"""
        if all(c.get('type') == 'code' for c in chunks):
            merged['language'] = chunks[0].get('language', 'unknown')
            merged['cell_type'] = 'code'
            merged['outputs'] = CellCombiner._collect_all_outputs(chunks)
            merged['has_output'] = len(merged['outputs']) > 0

    @staticmethod
    def _collect_all_outputs(chunks: List[Dict]) -> List:
        """Collect outputs from all chunks"""
        all_outputs = []
        for c in chunks:
            all_outputs.extend(c.get('outputs', []))
        return all_outputs
