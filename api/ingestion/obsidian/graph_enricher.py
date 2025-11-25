

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
        context_footer = GraphEnricher._build_context_footer(graph_meta, title)
        return [(f"{chunk_text}\n{context_footer}", page) for chunk_text, page in chunks]

    @staticmethod
    def _build_context_footer(graph_meta: Dict, title: str) -> str:
        """Build context footer with graph metadata"""
        context_lines = ["\n---", f"Note: {title}"]
        GraphEnricher._add_tags_line(graph_meta, context_lines)
        GraphEnricher._add_wikilinks_line(graph_meta, context_lines)
        GraphEnricher._add_backlinks_line(graph_meta, context_lines)
        GraphEnricher._add_connected_notes_line(graph_meta, context_lines)
        return '\n'.join(context_lines)

    @staticmethod
    def _add_tags_line(graph_meta: Dict, context_lines: List[str]):
        """Add tags line if tags exist"""
        if graph_meta['tags']:
            context_lines.append(f"Tags: {', '.join(graph_meta['tags'])}")

    @staticmethod
    def _add_wikilinks_line(graph_meta: Dict, context_lines: List[str]):
        """Add wikilinks line if links exist"""
        if graph_meta['wikilinks_out']:
            links_preview = GraphEnricher._format_wikilinks(graph_meta['wikilinks_out'])
            context_lines.append(f"Links to: {links_preview}")

    @staticmethod
    def _format_wikilinks(wikilinks: List[str]) -> str:
        """Format wikilinks with preview limit"""
        links_preview = ', '.join(wikilinks[:5])
        if len(wikilinks) > 5:
            links_preview += f" (+{len(wikilinks) - 5} more)"
        return links_preview

    @staticmethod
    def _add_backlinks_line(graph_meta: Dict, context_lines: List[str]):
        """Add backlinks count if any exist"""
        if graph_meta['backlinks_count'] > 0:
            context_lines.append(f"Linked from: {graph_meta['backlinks_count']} notes")

    @staticmethod
    def _add_connected_notes_line(graph_meta: Dict, context_lines: List[str]):
        """Add connected notes if any exist"""
        if graph_meta['connected_notes']:
            connected_preview = GraphEnricher._format_connected_notes(graph_meta['connected_notes'])
            context_lines.append(f"Related notes: {connected_preview}")

    @staticmethod
    def _format_connected_notes(connected_notes: List[str]) -> str:
        """Format connected notes with preview limit"""
        connected_preview = ', '.join(connected_notes[:3])
        if len(connected_notes) > 3:
            connected_preview += "..."
        return connected_preview
