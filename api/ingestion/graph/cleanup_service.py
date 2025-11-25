

import sqlite3
from typing import Dict

class CleanupService:
    """Handles graph cleanup and maintenance operations

    Single Responsibility: Graph data cleanup

    Manages:
    - Orphan node removal (tags, placeholders)
    - Node path updates (for file moves)
    - Graph clearing (for reindexing)
    - Graph statistics
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection

        Args:
            conn: SQLite database connection
        """
        self.conn = conn

    def cleanup_orphan_tags(self):
        """Delete tag nodes that have no incoming edges

        Tags are shared resources - only delete when no notes reference them.
        A tag is orphaned if it has zero incoming 'tag' edges.
        """
        self.conn.execute("""
            DELETE FROM graph_nodes
            WHERE node_type = 'tag'
            AND node_id NOT IN (
                SELECT DISTINCT target_id
                FROM graph_edges
                WHERE edge_type = 'tag'
            )
        """)

    def cleanup_orphan_placeholders(self):
        """Delete placeholder nodes (note_ref) with no incoming edges

        Placeholders are created for [[wikilink]] targets that don't exist yet.
        Delete them if no notes link to them anymore.
        """
        self.conn.execute("""
            DELETE FROM graph_nodes
            WHERE node_type = 'note_ref'
            AND node_id NOT IN (
                SELECT DISTINCT target_id
                FROM graph_edges
                WHERE edge_type = 'wikilink'
            )
        """)

    def update_note_path(self, old_path: str, new_path: str):
        """Update node IDs when a note file is moved (preserves graph structure)

        Updates all node IDs that contain the old path to use the new path.
        This includes note nodes, header nodes, and any path-based identifiers.
        Edges are automatically updated via CASCADE foreign keys.

        Args:
            old_path: Old file path
            new_path: New file path
        """
        try:
            old_node_ids = self._get_nodes_with_path(old_path)
            for old_id in old_node_ids:
                new_id = old_id.replace(old_path, new_path)
                self._update_node_id_across_tables(old_id, new_id)
        except Exception as e:
            print(f"Warning: Failed to update graph node paths: {e}")

    def _get_nodes_with_path(self, path: str) -> list:
        """Get all node IDs that contain the given path"""
        cursor = self.conn.execute("""
            SELECT node_id FROM graph_nodes WHERE node_id LIKE ?
        """, (f"%{path}%",))
        return [row[0] for row in cursor.fetchall()]

    def _update_node_id_across_tables(self, old_id: str, new_id: str):
        """Update a node ID across all graph tables"""
        self._update_node(old_id, new_id)
        self._update_edges_source(old_id, new_id)
        self._update_edges_target(old_id, new_id)
        self._update_metadata(old_id, new_id)
        self._update_chunk_links(old_id, new_id)

    def _update_node(self, old_id: str, new_id: str):
        """Update node ID in graph_nodes table"""
        self.conn.execute("""
            UPDATE graph_nodes SET node_id = ? WHERE node_id = ?
        """, (new_id, old_id))

    def _update_edges_source(self, old_id: str, new_id: str):
        """Update source_id in graph_edges table"""
        self.conn.execute("""
            UPDATE graph_edges SET source_id = ? WHERE source_id = ?
        """, (new_id, old_id))

    def _update_edges_target(self, old_id: str, new_id: str):
        """Update target_id in graph_edges table"""
        self.conn.execute("""
            UPDATE graph_edges SET target_id = ? WHERE target_id = ?
        """, (new_id, old_id))

    def _update_metadata(self, old_id: str, new_id: str):
        """Update node_id in graph_metadata table"""
        self.conn.execute("""
            UPDATE graph_metadata SET node_id = ? WHERE node_id = ?
        """, (new_id, old_id))

    def _update_chunk_links(self, old_id: str, new_id: str):
        """Update node_id in chunk_graph_links table"""
        self.conn.execute("""
            UPDATE chunk_graph_links SET node_id = ? WHERE node_id = ?
        """, (new_id, old_id))

    def clear_graph(self):
        """Clear all graph data (for reindexing)"""
        self.conn.execute("DELETE FROM chunk_graph_links")
        self.conn.execute("DELETE FROM graph_metadata")
        self.conn.execute("DELETE FROM graph_edges")
        self.conn.execute("DELETE FROM graph_nodes")

    def get_graph_stats(self) -> Dict:
        """Get graph statistics

        Returns:
            Dictionary with node counts, edge counts, and total counts
        """
        return {
            'nodes_by_type': self._get_nodes_by_type(),
            'edges_by_type': self._get_edges_by_type(),
            'total_nodes': self._get_total_nodes(),
            'total_edges': self._get_total_edges(),
            'total_chunk_links': self._get_total_chunk_links()
        }

    def _get_nodes_by_type(self) -> Dict:
        """Get node counts grouped by type"""
        cursor = self.conn.execute("""
            SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY node_type
        """)
        return dict(cursor.fetchall())

    def _get_edges_by_type(self) -> Dict:
        """Get edge counts grouped by type"""
        cursor = self.conn.execute("""
            SELECT edge_type, COUNT(*) FROM graph_edges GROUP BY edge_type
        """)
        return dict(cursor.fetchall())

    def _get_total_nodes(self) -> int:
        """Get total number of nodes"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM graph_nodes")
        return cursor.fetchone()[0]

    def _get_total_edges(self) -> int:
        """Get total number of edges"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM graph_edges")
        return cursor.fetchone()[0]

    def _get_total_chunk_links(self) -> int:
        """Get total number of chunk-graph links"""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunk_graph_links")
        return cursor.fetchone()[0]
