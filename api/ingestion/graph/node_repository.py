

import sqlite3
import json
from typing import Dict, Optional, Tuple

class NodeRepository:
    """Handles CRUD operations for graph nodes

    Single Responsibility: Node persistence

    Manages:
    - Node creation/updates
    - Node retrieval
    - Node deletion
    - Row-to-dict conversion
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection

        Args:
            conn: SQLite database connection
        """
        self.conn = conn

    def save(self, node_id: str, node_type: str, title: str,
             content: Optional[str] = None, metadata: Optional[Dict] = None):
        """Save or update a graph node

        Args:
            node_id: Unique node identifier
            node_type: Type of node (note, header, tag, placeholder)
            title: Node title/name
            content: Optional node content
            metadata: Optional metadata dictionary
        """
        self.conn.execute("""
            INSERT OR REPLACE INTO graph_nodes (node_id, node_type, title, content, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (node_id, node_type, title, content, json.dumps(metadata or {})))

    def get(self, node_id: str) -> Optional[Dict]:
        """Get node by ID

        Args:
            node_id: Node identifier

        Returns:
            Node dictionary or None if not found
        """
        cursor = self.conn.execute("""
            SELECT node_id, node_type, title, content, metadata
            FROM graph_nodes WHERE node_id = ?
        """, (node_id,))
        row = cursor.fetchone()
        return self._row_to_dict(row) if row else None

    def delete(self, node_id: str):
        """Delete a node

        Args:
            node_id: Node identifier to delete
        """
        self.conn.execute("DELETE FROM graph_nodes WHERE node_id = ?", (node_id,))

    def _row_to_dict(self, row: Tuple) -> Dict:
        """Convert node row to dictionary

        Args:
            row: Database row tuple

        Returns:
            Node dictionary with parsed metadata
        """
        return {
            'node_id': row[0],
            'node_type': row[1],
            'title': row[2],
            'content': row[3],
            'metadata': json.loads(row[4]) if row[4] else {}
        }
