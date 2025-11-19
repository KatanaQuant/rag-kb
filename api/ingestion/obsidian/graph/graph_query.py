"""Graph Query Helper - extracted from ObsidianGraphBuilder

POODR Phase 2.4: God Class Decomposition
- Extracted from ObsidianGraphBuilder
- Single Responsibility: Graph traversal and query operations
"""

import networkx as nx
from typing import List, Dict, Set, Optional


class GraphQuery:
    """Query operations for Obsidian knowledge graph

    Single Responsibility: Graph traversal and queries

    Handles:
    - Multi-hop node traversal
    - Backlink queries
    - Tag queries
    - Edge filtering by type
    """

    def get_connected_nodes(self, graph: nx.MultiDiGraph, node_id: str,
                           hops: int = 1,
                           edge_types: Optional[List[str]] = None) -> List[Dict]:
        """Get nodes connected within N hops

        Args:
            graph: NetworkX graph to query
            node_id: Starting node ID
            hops: Number of hops (1 = immediate neighbors, 2 = neighbors + their neighbors)
            edge_types: Filter by edge types (e.g., ['wikilink', 'backlink'])

        Returns:
            List of node dictionaries with metadata
        """
        if not graph.has_node(node_id):
            return []

        connected = {node_id}
        frontier = {node_id}

        for _ in range(hops):
            frontier = self._expand_frontier(graph, frontier, edge_types, connected)

        # Return node data for all connected nodes (except starting node)
        connected.discard(node_id)
        return [graph.nodes[nid] for nid in connected]

    def _expand_frontier(self, graph: nx.MultiDiGraph, frontier: Set[str],
                        edge_types: Optional[List[str]],
                        connected: Set[str]) -> Set[str]:
        """Expand frontier by one hop

        Args:
            graph: NetworkX graph
            frontier: Current frontier nodes
            edge_types: Optional edge type filter
            connected: Set of all visited nodes (updated in place)

        Returns:
            New frontier nodes
        """
        new_frontier = set()

        for node in frontier:
            neighbors = self._get_filtered_neighbors(graph, node, edge_types)
            new_neighbors = neighbors - connected
            new_frontier.update(new_neighbors)
            connected.update(new_neighbors)

        return new_frontier

    def _get_filtered_neighbors(self, graph: nx.MultiDiGraph, node_id: str,
                                edge_types: Optional[List[str]]) -> Set[str]:
        """Get neighbors filtered by edge type

        Args:
            graph: NetworkX graph
            node_id: Source node ID
            edge_types: Optional edge type filter

        Returns:
            Set of neighbor node IDs
        """
        if edge_types is None:
            return set(graph.neighbors(node_id))

        neighbors = set()
        for _, target, edge_data in graph.edges(node_id, data=True):
            if edge_data.get('edge_type') in edge_types:
                neighbors.add(target)

        return neighbors

    def get_backlinks(self, graph: nx.MultiDiGraph, node_id: str) -> List[str]:
        """Get all nodes that link TO this node

        Args:
            graph: NetworkX graph
            node_id: Target node ID

        Returns:
            List of source node IDs
        """
        if not graph.has_node(node_id):
            return []

        backlinks = []
        for source, target, edge_data in graph.edges(data=True):
            if target == node_id and edge_data.get('edge_type') == 'wikilink':
                backlinks.append(source)

        return backlinks

    def get_tags_for_note(self, graph: nx.MultiDiGraph, node_id: str) -> List[str]:
        """Get all tags for a note

        Args:
            graph: NetworkX graph
            node_id: Note node ID

        Returns:
            List of tag names (with # prefix)
        """
        if not graph.has_node(node_id):
            return []

        tags = []
        for _, target, edge_data in graph.edges(node_id, data=True):
            if edge_data.get('edge_type') == 'tag':
                tag_data = graph.nodes[target]
                tags.append(tag_data['title'])

        return tags

    def get_notes_with_tag(self, graph: nx.MultiDiGraph, tag: str) -> List[str]:
        """Get all notes with a specific tag

        Args:
            graph: NetworkX graph
            tag: Tag name (with or without # prefix)

        Returns:
            List of note node IDs
        """
        tag_id = f"tag:{tag.lstrip('#')}"

        if not graph.has_node(tag_id):
            return []

        notes = []
        for source, target, edge_data in graph.edges(data=True):
            if target == tag_id and edge_data.get('edge_type') == 'tag':
                notes.append(source)

        return notes
