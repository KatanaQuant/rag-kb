

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

            # Check if we should start a new group
            should_split = False

            # Hard boundary: markdown header
            if chunk.get('type') == 'markdown' and chunk.get('is_header'):
                should_split = True

            # Type change boundary (code <-> markdown)
            elif chunk.get('type') != current_group[0].get('type'):
                should_split = True

            # Size limit reached
            elif current_size + chunk_size > max_chunk_size:
                should_split = True

            if should_split:
                # Finalize current group
                if current_group:
                    combined.append(CellCombiner._merge_chunk_group(current_group))
                current_group = [chunk]
                current_size = chunk_size
            else:
                # Add to current group
                current_group.append(chunk)
                current_size += chunk_size

        # Add last group
        if current_group:
            combined.append(CellCombiner._merge_chunk_group(current_group))

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
