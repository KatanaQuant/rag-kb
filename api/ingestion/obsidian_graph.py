

import networkx as nx
from pathlib import Path
from typing import Dict, List, Optional
import json
from dataclasses import dataclass, field, asdict

from ingestion.obsidian.graph.wikilink_extractor import WikilinkExtractor
from ingestion.obsidian.graph.tag_extractor import TagExtractor
from ingestion.obsidian.graph.header_extractor import HeaderExtractor
from ingestion.obsidian.graph.graph_query import GraphQuery

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
    

    def __init__(self):
        
        self.graph = nx.MultiDiGraph()  # Supports multiple edges between nodes
        self.note_paths: Dict[str, Path] = {}  # title -> path mapping

        self.wikilink_extractor = WikilinkExtractor()
        self.tag_extractor = TagExtractor()
        self.header_extractor = HeaderExtractor()
        self.query = GraphQuery()

    def add_note(self, file_path: Path, title: str, content: str,
                 frontmatter: Optional[Dict] = None) -> str:
        """Add a note to the graph

        Orchestrates the full note ingestion pipeline:
        1. Create note node
        2. Extract wikilinks (delegate to WikilinkExtractor)
        3. Extract tags (delegate to TagExtractor)
        4. Extract headers (delegate to HeaderExtractor)

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

        # Delegate extraction to specialized components
        self.wikilink_extractor.extract_and_add(self.graph, node_id, content)
        self.tag_extractor.extract_and_add(self.graph, node_id, content)
        self.header_extractor.extract_and_add(self.graph, node_id, content)

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
        """Register note path for wikilink resolution"""
        self.note_paths[title] = file_path

    # ============================================================
    # QUERY OPERATIONS (delegate to GraphQuery)
    # ============================================================

    def get_connected_nodes(self, node_id: str, hops: int = 1,
                           edge_types: Optional[List[str]] = None) -> List[Dict]:
        """Get nodes connected within N hops

        Delegates to GraphQuery for traversal logic.
        """
        return self.query.get_connected_nodes(self.graph, node_id, hops, edge_types)

    def get_backlinks(self, node_id: str) -> List[str]:
        """Get all nodes that link TO this node

        Delegates to GraphQuery for backlink logic.
        """
        return self.query.get_backlinks(self.graph, node_id)

    def get_tags_for_note(self, node_id: str) -> List[str]:
        """Get all tags for a note

        Delegates to GraphQuery for tag retrieval.
        """
        return self.query.get_tags_for_note(self.graph, node_id)

    def get_notes_with_tag(self, tag: str) -> List[str]:
        """Get all notes with a specific tag

        Delegates to GraphQuery for tag search.
        """
        return self.query.get_notes_with_tag(self.graph, tag)

    # ============================================================
    # GRAPH ANALYTICS
    # ============================================================

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

    # ============================================================
    # GRAPH I/O OPERATIONS
    # ============================================================

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
