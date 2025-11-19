"""Edge Repository - extracted from GraphRepository

POODR Phase 2.3: Facade Pattern + Repository Decomposition
- Extracted from GraphRepository
- Single Responsibility: Edge CRUD operations
"""

import sqlite3
import json
from typing import List, Dict, Optional, Tuple


class EdgeRepository:
    """Handles CRUD operations for graph edges

    Single Responsibility: Edge persistence

    Manages:
    - Edge creation
    - Edge retrieval (from/to queries)
    - Row-to-dict conversion
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection

        Args:
            conn: SQLite database connection
        """
        self.conn = conn

    def save(self, source_id: str, target_id: str, edge_type: str,
             metadata: Optional[Dict] = None) -> int:
        """Save a graph edge

        Args:
            source_id: Source node identifier
            target_id: Target node identifier
            edge_type: Type of edge (wikilink, backlink, tag, etc.)
            metadata: Optional metadata dictionary

        Returns:
            Edge ID (lastrowid)
        """
        cursor = self.conn.execute("""
            INSERT INTO graph_edges (source_id, target_id, edge_type, metadata)
            VALUES (?, ?, ?, ?)
        """, (source_id, target_id, edge_type, json.dumps(metadata or {})))
        return cursor.lastrowid

    def get_from(self, source_id: str,
                 edge_type: Optional[str] = None) -> List[Dict]:
        """Get all edges from a source node

        Args:
            source_id: Source node identifier
            edge_type: Optional edge type filter

        Returns:
            List of edge dictionaries
        """
        if edge_type:
            query = """
                SELECT id, source_id, target_id, edge_type, metadata
                FROM graph_edges WHERE source_id = ? AND edge_type = ?
            """
            cursor = self.conn.execute(query, (source_id, edge_type))
        else:
            query = """
                SELECT id, source_id, target_id, edge_type, metadata
                FROM graph_edges WHERE source_id = ?
            """
            cursor = self.conn.execute(query, (source_id,))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def get_to(self, target_id: str,
               edge_type: Optional[str] = None) -> List[Dict]:
        """Get all edges to a target node

        Args:
            target_id: Target node identifier
            edge_type: Optional edge type filter

        Returns:
            List of edge dictionaries
        """
        if edge_type:
            query = """
                SELECT id, source_id, target_id, edge_type, metadata
                FROM graph_edges WHERE target_id = ? AND edge_type = ?
            """
            cursor = self.conn.execute(query, (target_id, edge_type))
        else:
            query = """
                SELECT id, source_id, target_id, edge_type, metadata
                FROM graph_edges WHERE target_id = ?
            """
            cursor = self.conn.execute(query, (target_id,))

        return [self._row_to_dict(row) for row in cursor.fetchall()]

    def _row_to_dict(self, row: Tuple) -> Dict:
        """Convert edge row to dictionary

        Args:
            row: Database row tuple

        Returns:
            Edge dictionary with parsed metadata
        """
        return {
            'id': row[0],
            'source_id': row[1],
            'target_id': row[2],
            'edge_type': row[3],
            'metadata': json.loads(row[4]) if row[4] else {}
        }
