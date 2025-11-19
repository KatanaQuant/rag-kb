"""Cleanup Service - extracted from GraphRepository

POODR Phase 2.3: Facade Pattern + Repository Decomposition
- Extracted from GraphRepository
- Single Responsibility: Graph cleanup and maintenance operations
"""

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
            # Get all nodes that contain the old path in their node_id
            cursor = self.conn.execute("""
                SELECT node_id FROM graph_nodes WHERE node_id LIKE ?
            """, (f"%{old_path}%",))
            old_node_ids = [row[0] for row in cursor.fetchall()]

            # Update each node's ID
            for old_id in old_node_ids:
                new_id = old_id.replace(old_path, new_path)

                # Update node
                self.conn.execute("""
                    UPDATE graph_nodes SET node_id = ? WHERE node_id = ?
                """, (new_id, old_id))

                # Update edges (source)
                self.conn.execute("""
                    UPDATE graph_edges SET source_id = ? WHERE source_id = ?
                """, (new_id, old_id))

                # Update edges (target)
                self.conn.execute("""
                    UPDATE graph_edges SET target_id = ? WHERE target_id = ?
                """, (new_id, old_id))

                # Update metadata
                self.conn.execute("""
                    UPDATE graph_metadata SET node_id = ? WHERE node_id = ?
                """, (new_id, old_id))

                # Update chunk_graph_links
                self.conn.execute("""
                    UPDATE chunk_graph_links SET node_id = ? WHERE node_id = ?
                """, (new_id, old_id))

        except Exception as e:
            print(f"Warning: Failed to update graph node paths: {e}")

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
        stats = {}

        # Node counts by type
        cursor = self.conn.execute("""
            SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY node_type
        """)
        stats['nodes_by_type'] = dict(cursor.fetchall())

        # Edge counts by type
        cursor = self.conn.execute("""
            SELECT edge_type, COUNT(*) FROM graph_edges GROUP BY edge_type
        """)
        stats['edges_by_type'] = dict(cursor.fetchall())

        # Total counts
        cursor = self.conn.execute("SELECT COUNT(*) FROM graph_nodes")
        stats['total_nodes'] = cursor.fetchone()[0]

        cursor = self.conn.execute("SELECT COUNT(*) FROM graph_edges")
        stats['total_edges'] = cursor.fetchone()[0]

        cursor = self.conn.execute("SELECT COUNT(*) FROM chunk_graph_links")
        stats['total_chunk_links'] = cursor.fetchone()[0]

        return stats
