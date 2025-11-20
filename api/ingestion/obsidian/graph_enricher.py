

from pathlib import Path
from typing import List, Tuple, Dict, Optional

class GraphEnricher:
    """Enrich chunks with knowledge graph metadata

    Single Responsibility: Add graph context to chunks

    Adds graph metadata directly to chunk text in a machine-readable format
    that embeddings can capture:
    - Note title
    - Tags
    - Wikilinks (outgoing)
    - Backlinks (incoming)
    - Connected notes
    """

    @staticmethod
    def enrich_chunks(chunks: List[Tuple[str, Optional[int]]],
                     graph_meta: Dict, title: str, path: Path) -> List[Tuple[str, Optional[int]]]:
        """Enrich chunks with graph context

        Adds graph metadata directly to chunk text in a machine-readable format
        that embeddings can capture.

        Args:
            chunks: List of (chunk_text, page_number) tuples
            graph_meta: Graph metadata dictionary with keys:
                - tags: List of tag strings
                - wikilinks_out: List of outgoing wikilink targets
                - backlinks_count: Number of incoming backlinks
                - connected_notes: List of connected note titles
            title: Note title
            path: Note path (not currently used)

        Returns:
            List of enriched (chunk_text, page_number) tuples
        """
        enriched = []

        for i, (chunk_text, page) in enumerate(chunks):
            # Build context footer
            context_lines = [
                f"\n---",
                f"Note: {title}",
            ]

            if graph_meta['tags']:
                context_lines.append(f"Tags: {', '.join(graph_meta['tags'])}")

            if graph_meta['wikilinks_out']:
                links_preview = ', '.join(graph_meta['wikilinks_out'][:5])
                if len(graph_meta['wikilinks_out']) > 5:
                    links_preview += f" (+{len(graph_meta['wikilinks_out']) - 5} more)"
                context_lines.append(f"Links to: {links_preview}")

            if graph_meta['backlinks_count'] > 0:
                context_lines.append(f"Linked from: {graph_meta['backlinks_count']} notes")

            if graph_meta['connected_notes']:
                connected_preview = ', '.join(graph_meta['connected_notes'][:3])
                if len(graph_meta['connected_notes']) > 3:
                    connected_preview += "..."
                context_lines.append(f"Related notes: {connected_preview}")

            # Add context to chunk
            context_footer = '\n'.join(context_lines)
            enriched_text = f"{chunk_text}\n{context_footer}"

            enriched.append((enriched_text, page))

        return enriched
