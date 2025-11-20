

import re
import networkx as nx
from typing import Optional

class WikilinkExtractor:
    """Extract wikilinks from markdown and build graph edges

    Single Responsibility: Wikilink extraction and edge creation

    Handles:
    - [[wikilink]] pattern matching
    - Alias support [[target|alias]]
    - Placeholder node creation
    - Bidirectional edge creation (wikilink + backlink)
    """

    def __init__(self):
        """Initialize with wikilink pattern"""
        self.wikilink_pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

    def extract_and_add(self, graph: nx.MultiDiGraph, source_id: str, content: str):
        """Extract wikilinks and add as edges to graph

        Args:
            graph: NetworkX graph to add edges to
            source_id: Source node ID (note)
            content: Markdown content to extract from
        """
        matches = self.wikilink_pattern.findall(content)
        for target_title, alias in matches:
            self._add_wikilink_edge(graph, source_id, target_title.strip(), alias)

    def _add_wikilink_edge(self, graph: nx.MultiDiGraph, source_id: str,
                          target_title: str, alias: Optional[str]):
        """Add wikilink edge (will create target node if needed)

        Creates bidirectional edges:
        - source -> target (type: wikilink)
        - target -> source (type: backlink)

        Args:
            graph: NetworkX graph
            source_id: Source node ID
            target_title: Target note title
            alias: Optional display alias
        """
        target_id = f"note_ref:{target_title}"

        # Add target node if not exists (placeholder until we process that note)
        if not graph.has_node(target_id):
            self._add_placeholder_node(graph, target_id, target_title)

        # Add bidirectional edge
        edge_meta = {'alias': alias} if alias else {}
        graph.add_edge(source_id, target_id, edge_type='wikilink', **edge_meta)
        graph.add_edge(target_id, source_id, edge_type='backlink', **edge_meta)

    def _add_placeholder_node(self, graph: nx.MultiDiGraph, node_id: str, title: str):
        """Add placeholder node for referenced but not yet processed notes

        Args:
            graph: NetworkX graph
            node_id: Node identifier
            title: Note title
        """
        graph.add_node(node_id,
                      node_id=node_id,
                      node_type='note_ref',
                      title=title,
                      content=None,
                      metadata={'placeholder': True})
