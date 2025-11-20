

import sqlite3
from typing import List, Dict, Optional
from pathlib import Path

from ingestion.graph.node_repository import NodeRepository
from ingestion.graph.edge_repository import EdgeRepository
from ingestion.graph.metadata_repository import MetadataRepository
from ingestion.graph.cleanup_service import CleanupService

class GraphRepository:
    

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection

        Creates all specialized repositories with shared connection.

        Args:
            conn: SQLite database connection
        """
        self.conn = conn
        self.nodes = NodeRepository(conn)
        self.edges = EdgeRepository(conn)
        self.metadata = MetadataRepository(conn)
        self.cleanup = CleanupService(conn)

    # ============================================================
    # NODE OPERATIONS (delegate to NodeRepository)
    # ============================================================

    def save_node(self, node_id: str, node_type: str, title: str,
                  content: Optional[str] = None, metadata: Optional[Dict] = None):
        """Save or update a graph node"""
        self.nodes.save(node_id, node_type, title, content, metadata)

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID"""
        return self.nodes.get(node_id)

    def delete_node(self, node_id: str):
        """Delete a node (cascades to edges and links)"""
        self.nodes.delete(node_id)

    # ============================================================
    # EDGE OPERATIONS (delegate to EdgeRepository)
    # ============================================================

    def save_edge(self, source_id: str, target_id: str, edge_type: str,
                  metadata: Optional[Dict] = None) -> int:
        """Save a graph edge"""
        return self.edges.save(source_id, target_id, edge_type, metadata)

    def get_edges_from(self, source_id: str,
                       edge_type: Optional[str] = None) -> List[Dict]:
        """Get all edges from a source node"""
        return self.edges.get_from(source_id, edge_type)

    def get_edges_to(self, target_id: str,
                     edge_type: Optional[str] = None) -> List[Dict]:
        """Get all edges to a target node"""
        return self.edges.get_to(target_id, edge_type)

    # ============================================================
    # METADATA OPERATIONS (delegate to MetadataRepository)
    # ============================================================

    def save_pagerank_scores(self, scores: Dict[str, float]):
        """Save PageRank scores for all nodes"""
        self.metadata.save_pagerank_scores(scores)

    def get_pagerank_score(self, node_id: str) -> Optional[float]:
        """Get PageRank score for a node"""
        return self.metadata.get_pagerank_score(node_id)

    def link_chunk_to_node(self, chunk_id: int, node_id: str,
                           link_type: str = 'primary'):
        """Link a chunk to a graph node"""
        self.metadata.link_chunk_to_node(chunk_id, node_id, link_type)

    def get_nodes_for_chunk(self, chunk_id: int) -> List[Dict]:
        """Get all graph nodes linked to a chunk"""
        return self.metadata.get_nodes_for_chunk(chunk_id)

    def get_chunks_for_node(self, node_id: str) -> List[int]:
        """Get all chunk IDs linked to a node"""
        return self.metadata.get_chunks_for_node(node_id)

    # ============================================================
    # CLEANUP OPERATIONS (delegate to CleanupService)
    # ============================================================

    def cleanup_orphan_tags(self):
        """Delete tag nodes that have no incoming edges"""
        self.cleanup.cleanup_orphan_tags()

    def cleanup_orphan_placeholders(self):
        """Delete placeholder nodes (note_ref) with no incoming edges"""
        self.cleanup.cleanup_orphan_placeholders()

    def update_note_path(self, old_path: str, new_path: str):
        """Update node IDs when a note file is moved"""
        self.cleanup.update_note_path(old_path, new_path)

    def clear_graph(self):
        """Clear all graph data (for reindexing)"""
        self.cleanup.clear_graph()

    def get_graph_stats(self) -> Dict:
        """Get graph statistics"""
        return self.cleanup.get_graph_stats()

    # ============================================================
    # ORCHESTRATION METHODS (complex operations using multiple repos)
    # ============================================================

    def delete_note_nodes(self, note_path: str):
        """Delete all nodes associated with a note (on reindex)

        Orchestrates:
        1. Delete primary note node and headers (NodeRepository)
        2. Clean up orphaned tags (CleanupService)
        3. Clean up orphaned placeholders (CleanupService)

        Args:
            note_path: Path to note file
        """
        note_id = f"note:{note_path}"

        # Delete note node and headers (CASCADE handles edges)
        self._delete_note_and_headers(note_id)

        # Clean up orphaned shared nodes
        self.cleanup.cleanup_orphan_tags()
        self.cleanup.cleanup_orphan_placeholders()

    def _delete_note_and_headers(self, note_id: str):
        """Delete note node and all its header children

        Internal helper for delete_note_nodes orchestration.
        """
        # Headers have node_id pattern: note:path:h0, note:path:h1, etc.
        self.conn.execute("""
            DELETE FROM graph_nodes
            WHERE node_id = ? OR node_id LIKE ?
        """, (note_id, f"{note_id}:h%"))

    def get_connected_nodes_multi_hop(self, node_id: str, hops: int = 1,
                                      edge_types: Optional[List[str]] = None) -> List[Dict]:
        """Get nodes connected within N hops via SQL

        Orchestrates multi-hop graph traversal using EdgeRepository and NodeRepository.
        More efficient than building NetworkX graph for simple queries.

        Args:
            node_id: Starting node
            hops: Number of hops (default 1)
            edge_types: Optional list of edge types to filter

        Returns:
            List of connected node dictionaries
        """
        visited = {node_id}
        frontier = {node_id}

        for _ in range(hops):
            if not frontier:
                break
            frontier = self._expand_frontier_sql(frontier, edge_types, visited)

        # Remove starting node
        visited.discard(node_id)

        # Get node data for all connected nodes
        if not visited:
            return []

        placeholders = ','.join('?' * len(visited))
        query = f"""
            SELECT node_id, node_type, title, content, metadata
            FROM graph_nodes WHERE node_id IN ({placeholders})
        """
        cursor = self.conn.execute(query, tuple(visited))
        return [self.nodes._row_to_dict(row) for row in cursor.fetchall()]

    def _expand_frontier_sql(self, frontier: set, edge_types: Optional[List[str]],
                            visited: set) -> set:
        """Expand frontier by one hop via SQL

        Internal helper for get_connected_nodes_multi_hop orchestration.
        """
        if not frontier:
            return set()

        placeholders = ','.join('?' * len(frontier))

        if edge_types:
            type_placeholders = ','.join('?' * len(edge_types))
            query = f"""
                SELECT DISTINCT target_id FROM graph_edges
                WHERE source_id IN ({placeholders})
                AND edge_type IN ({type_placeholders})
            """
            params = tuple(frontier) + tuple(edge_types)
        else:
            query = f"""
                SELECT DISTINCT target_id FROM graph_edges
                WHERE source_id IN ({placeholders})
            """
            params = tuple(frontier)

        cursor = self.conn.execute(query, params)
        new_nodes = {row[0] for row in cursor.fetchall()}
        new_frontier = new_nodes - visited
        visited.update(new_frontier)
        return new_frontier

    def persist_graph(self, graph_export: Dict):
        """Persist entire graph from ObsidianGraphBuilder export

        Orchestrates bulk import using NodeRepository and EdgeRepository.

        Args:
            graph_export: Dictionary from ObsidianGraphBuilder.export_graph()
                         with 'nodes' and 'edges' keys
        """
        if not graph_export:
            return

        # Persist nodes
        for node_data in graph_export.get('nodes', []):
            node_id = node_data.get('id')
            node_type = node_data.get('node_type', 'unknown')
            title = node_data.get('title', '')
            content = node_data.get('content')
            metadata = {k: v for k, v in node_data.items()
                       if k not in ['id', 'node_type', 'title', 'content']}

            self.nodes.save(node_id, node_type, title, content, metadata)

        # Persist edges
        for edge_data in graph_export.get('edges', []):
            source = edge_data.get('source')
            target = edge_data.get('target')
            edge_type = edge_data.get('type', 'unknown')
            metadata = {k: v for k, v in edge_data.items()
                       if k not in ['source', 'target', 'type']}

            self.edges.save(source, target, edge_type, metadata)

    def commit(self):
        """Commit transaction"""
        self.conn.commit()
