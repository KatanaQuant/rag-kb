"""Tag Extractor - extracted from ObsidianGraphBuilder

POODR Phase 2.4: God Class Decomposition
- Extracted from ObsidianGraphBuilder
- Single Responsibility: Extract tags and build tag nodes
"""

import re
import networkx as nx


class TagExtractor:
    """Extract tags from markdown and build graph nodes

    Single Responsibility: Tag extraction and node creation

    Handles:
    - #tag pattern matching
    - Nested tags (#tag/subtag)
    - Tag node creation (shared resources)
    - Tag-to-note edges
    """

    def __init__(self):
        """Initialize with tag pattern"""
        self.tag_pattern = re.compile(r'#([\w/\-]+)')

    def extract_and_add(self, graph: nx.MultiDiGraph, note_id: str, content: str):
        """Extract tags and add as nodes + edges to graph

        Args:
            graph: NetworkX graph to add nodes/edges to
            note_id: Source note ID
            content: Markdown content to extract from
        """
        matches = self.tag_pattern.findall(content)
        unique_tags = set(matches)

        for tag in unique_tags:
            self._add_tag_node_and_edge(graph, note_id, tag)

    def _add_tag_node_and_edge(self, graph: nx.MultiDiGraph,
                               note_id: str, tag: str):
        """Add tag node and connect to note

        Tags are shared resources - only create if not exists.

        Args:
            graph: NetworkX graph
            note_id: Source note ID
            tag: Tag name (without # prefix)
        """
        tag_id = f"tag:{tag}"

        # Add tag node if not exists
        if not graph.has_node(tag_id):
            graph.add_node(tag_id,
                          node_id=tag_id,
                          node_type='tag',
                          title=f"#{tag}",
                          content=None,
                          metadata={'tag_name': tag})

        # Add edge from note to tag
        graph.add_edge(note_id, tag_id, edge_type='tag')
