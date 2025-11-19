"""Header Extractor - extracted from ObsidianGraphBuilder

POODR Phase 2.4: God Class Decomposition
- Extracted from ObsidianGraphBuilder (CC 5)
- Single Responsibility: Extract headers and build hierarchical nodes
"""

import re
import networkx as nx
from typing import List, Tuple


class HeaderExtractor:
    """Extract markdown headers and build hierarchical graph nodes

    Single Responsibility: Header extraction and hierarchy building

    Handles:
    - Markdown header parsing (# ## ### etc.)
    - Header hierarchy tracking (parent-child relationships)
    - Header node creation with hierarchy metadata
    - Header-to-parent edges
    """

    def extract_and_add(self, graph: nx.MultiDiGraph, note_id: str, content: str):
        """Extract markdown headers and add as hierarchical nodes

        Builds header hierarchy based on heading levels:
        - # Top Level (level 1)
          - ## Sublevel (level 2)
            - ### Sub-sublevel (level 3)

        Args:
            graph: NetworkX graph to add nodes/edges to
            note_id: Parent note ID
            content: Markdown content to extract from
        """
        header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        matches = header_pattern.findall(content)

        parent_id = note_id
        header_stack = [(0, note_id)]  # (level, id) stack for hierarchy

        for i, (hashes, title) in enumerate(matches):
            level = len(hashes)
            header_id = f"{note_id}:h{i}"

            # Find parent (most recent header with level < current)
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            parent_id = header_stack[-1][1] if header_stack else note_id

            self._add_header_node(graph, header_id, title, level, parent_id)
            header_stack.append((level, header_id))

    def _add_header_node(self, graph: nx.MultiDiGraph, header_id: str,
                        title: str, level: int, parent_id: str):
        """Add header node and connect to parent

        Args:
            graph: NetworkX graph
            header_id: Header node ID
            title: Header text
            level: Header level (1-6)
            parent_id: Parent node ID (note or parent header)
        """
        graph.add_node(header_id,
                      node_id=header_id,
                      node_type='header',
                      title=title,
                      content=None,
                      metadata={
                          'level': level,
                          'parent_id': parent_id
                      })

        # Connect to parent
        graph.add_edge(parent_id, header_id, edge_type='header_child')
