

import sqlite3
import json
from typing import List, Dict, Optional

class MetadataRepository:
    """Handles graph metadata and chunk-node link operations

    Single Responsibility: Metadata persistence

    Manages:
    - PageRank scores (graph_metadata table)
    - Chunk-to-node links (chunk_graph_links table)
    - Node-to-chunk lookups
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection

        Args:
            conn: SQLite database connection
        """
        self.conn = conn

    def save_pagerank_scores(self, scores: Dict[str, float]):
        """Save PageRank scores for all nodes

        Args:
            scores: Dictionary mapping node_id to PageRank score
        """
        for node_id, score in scores.items():
            self.conn.execute("""
                INSERT OR REPLACE INTO graph_metadata (node_id, pagerank_score)
                VALUES (?, ?)
            """, (node_id, score))

    def get_pagerank_score(self, node_id: str) -> Optional[float]:
        """Get PageRank score for a node

        Args:
            node_id: Node identifier

        Returns:
            PageRank score or None if not computed
        """
        cursor = self.conn.execute("""
            SELECT pagerank_score FROM graph_metadata WHERE node_id = ?
        """, (node_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def link_chunk_to_node(self, chunk_id: int, node_id: str,
                           link_type: str = 'primary'):
        """Link a chunk to a graph node

        Args:
            chunk_id: Chunk identifier (from chunks table)
            node_id: Graph node identifier
            link_type: Type of link (primary, reference, tag, etc.)
        """
        self.conn.execute("""
            INSERT INTO chunk_graph_links (chunk_id, node_id, link_type)
            VALUES (?, ?, ?)
        """, (chunk_id, node_id, link_type))

    def get_nodes_for_chunk(self, chunk_id: int) -> List[Dict]:
        """Get all graph nodes linked to a chunk

        Args:
            chunk_id: Chunk identifier

        Returns:
            List of node dictionaries with link_type included
        """
        cursor = self.conn.execute("""
            SELECT gn.node_id, gn.node_type, gn.title, gn.content, gn.metadata, cgl.link_type
            FROM chunk_graph_links cgl
            JOIN graph_nodes gn ON cgl.node_id = gn.node_id
            WHERE cgl.chunk_id = ?
        """, (chunk_id,))

        results = []
        for row in cursor.fetchall():
            node = {
                'node_id': row[0],
                'node_type': row[1],
                'title': row[2],
                'content': row[3],
                'metadata': json.loads(row[4]) if row[4] else {},
                'link_type': row[5]
            }
            results.append(node)
        return results

    def get_chunks_for_node(self, node_id: str) -> List[int]:
        """Get all chunk IDs linked to a node

        Args:
            node_id: Graph node identifier

        Returns:
            List of chunk IDs
        """
        cursor = self.conn.execute("""
            SELECT chunk_id FROM chunk_graph_links WHERE node_id = ?
        """, (node_id,))
        return [row[0] for row in cursor.fetchall()]
