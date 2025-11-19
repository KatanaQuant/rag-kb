"""Obsidian Knowledge Graph Builder and Manager

Builds and manages a NetworkX graph representing:
- Notes as nodes
- Wikilinks as edges (bidirectional)
- Tags as nodes connected to notes
- Headers as hierarchical nodes within notes
- Shared concepts as edges

Supports multi-hop graph traversal for enriched RAG retrieval.
"""

import networkx as nx
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import json
import re
from dataclasses import dataclass, field, asdict


@dataclass
class ObsidianNode:
    """Represents a node in the Obsidian knowledge graph"""
    node_id: str  # Unique identifier (file path or tag name)
    node_type: str  # 'note', 'tag', 'header', 'concept'
    title: str  # Display name
    content: Optional[str] = None  # For notes/headers: first 200 chars
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return asdict(self)


@dataclass
class ObsidianEdge:
    """Represents an edge in the Obsidian knowledge graph"""
    source: str  # Source node ID
    target: str  # Target node ID
    edge_type: str  # 'wikilink', 'tag', 'header_child', 'concept'
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return asdict(self)


class ObsidianGraphBuilder:
    """Builds knowledge graph from Obsidian vault structure

    Architecture follows Sandi Metz principles:
    - Small, focused methods (<10 lines each)
    - Single responsibility per method
    - Clear separation of concerns
    """

    def __init__(self):
        self.graph = nx.MultiDiGraph()  # Supports multiple edges between nodes
        self.note_paths: Dict[str, Path] = {}  # title -> path mapping
        self.wikilink_pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
        self.tag_pattern = re.compile(r'#([\w/\-]+)')

    def add_note(self, file_path: Path, title: str, content: str,
                 frontmatter: Optional[Dict] = None) -> str:
        """Add a note to the graph

        Args:
            file_path: Path to the note file
            title: Note title (filename without extension)
            content: Full note content
            frontmatter: Optional YAML frontmatter

        Returns:
            node_id: The unique node ID for this note
        """
        node_id = self._create_note_id(file_path)
        self._add_note_node(node_id, title, content, frontmatter)
        self._register_note_path(title, file_path)
        self._extract_and_add_wikilinks(node_id, content)
        self._extract_and_add_tags(node_id, content)
        self._extract_and_add_headers(node_id, content)
        return node_id

    def _create_note_id(self, file_path: Path) -> str:
        """Create unique node ID from file path"""
        return f"note:{file_path.as_posix()}"

    def _add_note_node(self, node_id: str, title: str, content: str,
                       frontmatter: Optional[Dict]):
        """Add note node to graph"""
        preview = content[:200] if content else ""
        node = ObsidianNode(
            node_id=node_id,
            node_type='note',
            title=title,
            content=preview,
            metadata={
                'frontmatter': frontmatter or {},
                'length': len(content),
                'has_frontmatter': frontmatter is not None
            }
        )
        self.graph.add_node(node_id, **node.to_dict())

    def _register_note_path(self, title: str, file_path: Path):
        """Register title -> path mapping for wikilink resolution"""
        self.note_paths[title] = file_path

    def _extract_and_add_wikilinks(self, source_id: str, content: str):
        """Extract wikilinks and add as edges"""
        matches = self.wikilink_pattern.findall(content)
        for target_title, alias in matches:
            self._add_wikilink_edge(source_id, target_title.strip(), alias)

    def _add_wikilink_edge(self, source_id: str, target_title: str,
                           alias: Optional[str]):
        """Add wikilink edge (will create target node if needed)"""
        target_id = f"note_ref:{target_title}"

        # Add target node if not exists (placeholder until we process that note)
        if not self.graph.has_node(target_id):
            self._add_placeholder_node(target_id, target_title)

        # Add bidirectional edge
        edge_meta = {'alias': alias} if alias else {}
        self.graph.add_edge(source_id, target_id, edge_type='wikilink',
                           **edge_meta)
        self.graph.add_edge(target_id, source_id, edge_type='backlink',
                           **edge_meta)

    def _add_placeholder_node(self, node_id: str, title: str):
        """Add placeholder node for referenced but not yet processed notes"""
        node = ObsidianNode(
            node_id=node_id,
            node_type='note_ref',
            title=title,
            metadata={'placeholder': True}
        )
        self.graph.add_node(node_id, **node.to_dict())

    def _extract_and_add_tags(self, note_id: str, content: str):
        """Extract tags and add as nodes + edges"""
        matches = self.tag_pattern.findall(content)
        unique_tags = set(matches)

        for tag in unique_tags:
            self._add_tag_node_and_edge(note_id, tag)

    def _add_tag_node_and_edge(self, note_id: str, tag: str):
        """Add tag node and connect to note"""
        tag_id = f"tag:{tag}"

        # Add tag node if not exists
        if not self.graph.has_node(tag_id):
            node = ObsidianNode(
                node_id=tag_id,
                node_type='tag',
                title=f"#{tag}",
                metadata={'tag_name': tag}
            )
            self.graph.add_node(tag_id, **node.to_dict())

        # Add edge from note to tag
        self.graph.add_edge(note_id, tag_id, edge_type='tag')

    def _extract_and_add_headers(self, note_id: str, content: str):
        """Extract markdown headers and add as hierarchical nodes"""
        header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        matches = header_pattern.findall(content)

        parent_id = note_id
        prev_level = 0
        header_stack = [(0, note_id)]  # (level, id) stack

        for i, (hashes, title) in enumerate(matches):
            level = len(hashes)
            header_id = f"{note_id}:h{i}"

            # Find parent (most recent header with level < current)
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            parent_id = header_stack[-1][1] if header_stack else note_id

            self._add_header_node(header_id, title, level, parent_id)
            header_stack.append((level, header_id))

    def _add_header_node(self, header_id: str, title: str, level: int,
                        parent_id: str):
        """Add header node and connect to parent"""
        node = ObsidianNode(
            node_id=header_id,
            node_type='header',
            title=title,
            metadata={'level': level}
        )
        self.graph.add_node(header_id, **node.to_dict())
        self.graph.add_edge(parent_id, header_id, edge_type='header_child')

    def get_connected_nodes(self, node_id: str, hops: int = 1,
                           edge_types: Optional[List[str]] = None) -> List[Dict]:
        """Get nodes connected within N hops

        Args:
            node_id: Starting node ID
            hops: Number of hops (1 = immediate neighbors, 2 = neighbors + their neighbors)
            edge_types: Filter by edge types (e.g., ['wikilink', 'backlink'])

        Returns:
            List of node dictionaries with metadata
        """
        if not self.graph.has_node(node_id):
            return []

        connected = set([node_id])
        frontier = {node_id}

        for _ in range(hops):
            frontier = self._expand_frontier(frontier, edge_types, connected)

        # Return node data for all connected nodes (except starting node)
        connected.discard(node_id)
        return [self.graph.nodes[nid] for nid in connected]

    def _expand_frontier(self, frontier: Set[str], edge_types: Optional[List[str]],
                        connected: Set[str]) -> Set[str]:
        """Expand frontier by one hop"""
        new_frontier = set()

        for node in frontier:
            neighbors = self._get_filtered_neighbors(node, edge_types)
            new_neighbors = neighbors - connected
            new_frontier.update(new_neighbors)
            connected.update(new_neighbors)

        return new_frontier

    def _get_filtered_neighbors(self, node_id: str,
                                edge_types: Optional[List[str]]) -> Set[str]:
        """Get neighbors filtered by edge type"""
        if edge_types is None:
            return set(self.graph.neighbors(node_id))

        neighbors = set()
        for _, target, edge_data in self.graph.edges(node_id, data=True):
            if edge_data.get('edge_type') in edge_types:
                neighbors.add(target)

        return neighbors

    def get_backlinks(self, node_id: str) -> List[str]:
        """Get all nodes that link TO this node"""
        if not self.graph.has_node(node_id):
            return []

        backlinks = []
        for source, target, edge_data in self.graph.edges(data=True):
            if target == node_id and edge_data.get('edge_type') == 'wikilink':
                backlinks.append(source)

        return backlinks

    def get_tags_for_note(self, node_id: str) -> List[str]:
        """Get all tags for a note"""
        if not self.graph.has_node(node_id):
            return []

        tags = []
        for _, target, edge_data in self.graph.edges(node_id, data=True):
            if edge_data.get('edge_type') == 'tag':
                tag_data = self.graph.nodes[target]
                tags.append(tag_data['title'])

        return tags

    def get_notes_with_tag(self, tag: str) -> List[str]:
        """Get all notes with a specific tag"""
        tag_id = f"tag:{tag.lstrip('#')}"

        if not self.graph.has_node(tag_id):
            return []

        notes = []
        for source, target, edge_data in self.graph.edges(data=True):
            if target == tag_id and edge_data.get('edge_type') == 'tag':
                notes.append(source)

        return notes

    def compute_pagerank(self, max_iter: int = 100) -> Dict[str, float]:
        """Compute PageRank scores for all nodes

        Higher scores = more central/important nodes
        Useful for ranking search results
        """
        try:
            return nx.pagerank(self.graph, max_iter=max_iter)
        except:
            # Return uniform scores if PageRank fails
            return {node: 1.0 / len(self.graph.nodes)
                    for node in self.graph.nodes}

    def export_graph(self) -> Dict:
        """Export graph to JSON-serializable format"""
        return {
            'nodes': [
                {**self.graph.nodes[node], 'id': node}
                for node in self.graph.nodes
            ],
            'edges': [
                {
                    'source': u,
                    'target': v,
                    'type': data.get('edge_type'),
                    **{k: v for k, v in data.items() if k != 'edge_type'}
                }
                for u, v, data in self.graph.edges(data=True)
            ],
            'stats': {
                'total_nodes': self.graph.number_of_nodes(),
                'total_edges': self.graph.number_of_edges(),
                'node_types': self._count_node_types(),
                'edge_types': self._count_edge_types()
            }
        }

    def _count_node_types(self) -> Dict[str, int]:
        """Count nodes by type"""
        counts = {}
        for node, data in self.graph.nodes(data=True):
            node_type = data.get('node_type', 'unknown')
            counts[node_type] = counts.get(node_type, 0) + 1
        return counts

    def _count_edge_types(self) -> Dict[str, int]:
        """Count edges by type"""
        counts = {}
        for _, _, data in self.graph.edges(data=True):
            edge_type = data.get('edge_type', 'unknown')
            counts[edge_type] = counts.get(edge_type, 0) + 1
        return counts

    def import_graph(self, graph_data: Dict):
        """Import graph from JSON format"""
        self.graph.clear()

        # Add nodes
        for node_data in graph_data.get('nodes', []):
            node_id = node_data.pop('id')
            self.graph.add_node(node_id, **node_data)

        # Add edges
        for edge_data in graph_data.get('edges', []):
            source = edge_data.pop('source')
            target = edge_data.pop('target')
            self.graph.add_edge(source, target, **edge_data)

    def save_to_file(self, path: Path):
        """Save graph to JSON file"""
        graph_data = self.export_graph()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2, ensure_ascii=False)

    def load_from_file(self, path: Path):
        """Load graph from JSON file"""
        with open(path, 'r', encoding='utf-8') as f:
            graph_data = json.load(f)
        self.import_graph(graph_data)
