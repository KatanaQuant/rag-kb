"""Graph Repository for Obsidian Knowledge Graph Database Operations

Handles CRUD operations for graph nodes, edges, and metadata.
Provides persistence layer for NetworkX graphs.
"""

import sqlite3
import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class GraphRepository:
    """Database operations for knowledge graph

    Follows Sandi Metz principles:
    - Small focused methods
    - Single responsibility
    - No method >10 lines
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_node(self, node_id: str, node_type: str, title: str,
                  content: Optional[str] = None, metadata: Optional[Dict] = None):
        """Save or update a graph node"""
        self.conn.execute("""
            INSERT OR REPLACE INTO graph_nodes (node_id, node_type, title, content, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (node_id, node_type, title, content, json.dumps(metadata or {})))

    def save_edge(self, source_id: str, target_id: str, edge_type: str,
                  metadata: Optional[Dict] = None) -> int:
        """Save a graph edge"""
        cursor = self.conn.execute("""
            INSERT INTO graph_edges (source_id, target_id, edge_type, metadata)
            VALUES (?, ?, ?, ?)
        """, (source_id, target_id, edge_type, json.dumps(metadata or {})))
        return cursor.lastrowid

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID"""
        cursor = self.conn.execute("""
            SELECT node_id, node_type, title, content, metadata
            FROM graph_nodes WHERE node_id = ?
        """, (node_id,))
        row = cursor.fetchone()
        return self._node_row_to_dict(row) if row else None

    def _node_row_to_dict(self, row: Tuple) -> Dict:
        """Convert node row to dictionary"""
        return {
            'node_id': row[0],
            'node_type': row[1],
            'title': row[2],
            'content': row[3],
            'metadata': json.loads(row[4]) if row[4] else {}
        }

    def get_edges_from(self, source_id: str,
                       edge_type: Optional[str] = None) -> List[Dict]:
        """Get all edges from a source node"""
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

        return [self._edge_row_to_dict(row) for row in cursor.fetchall()]

    def get_edges_to(self, target_id: str,
                     edge_type: Optional[str] = None) -> List[Dict]:
        """Get all edges to a target node"""
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

        return [self._edge_row_to_dict(row) for row in cursor.fetchall()]

    def _edge_row_to_dict(self, row: Tuple) -> Dict:
        """Convert edge row to dictionary"""
        return {
            'id': row[0],
            'source_id': row[1],
            'target_id': row[2],
            'edge_type': row[3],
            'metadata': json.loads(row[4]) if row[4] else {}
        }

    def save_pagerank_scores(self, scores: Dict[str, float]):
        """Save PageRank scores for all nodes"""
        for node_id, score in scores.items():
            self.conn.execute("""
                INSERT OR REPLACE INTO graph_metadata (node_id, pagerank_score)
                VALUES (?, ?)
            """, (node_id, score))

    def get_pagerank_score(self, node_id: str) -> Optional[float]:
        """Get PageRank score for a node"""
        cursor = self.conn.execute("""
            SELECT pagerank_score FROM graph_metadata WHERE node_id = ?
        """, (node_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def link_chunk_to_node(self, chunk_id: int, node_id: str,
                           link_type: str = 'primary'):
        """Link a chunk to a graph node"""
        self.conn.execute("""
            INSERT INTO chunk_graph_links (chunk_id, node_id, link_type)
            VALUES (?, ?, ?)
        """, (chunk_id, node_id, link_type))

    def get_nodes_for_chunk(self, chunk_id: int) -> List[Dict]:
        """Get all graph nodes linked to a chunk"""
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
        """Get all chunk IDs linked to a node"""
        cursor = self.conn.execute("""
            SELECT chunk_id FROM chunk_graph_links WHERE node_id = ?
        """, (node_id,))
        return [row[0] for row in cursor.fetchall()]

    def get_connected_nodes_multi_hop(self, node_id: str, hops: int = 1,
                                      edge_types: Optional[List[str]] = None) -> List[Dict]:
        """Get nodes connected within N hops via SQL

        More efficient than building NetworkX graph for simple queries.
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
        return [self._node_row_to_dict(row) for row in cursor.fetchall()]

    def _expand_frontier_sql(self, frontier: set, edge_types: Optional[List[str]],
                            visited: set) -> set:
        """Expand frontier by one hop via SQL"""
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

    def delete_node(self, node_id: str):
        """Delete a node (cascades to edges and links)"""
        self.conn.execute("DELETE FROM graph_nodes WHERE node_id = ?", (node_id,))

    def delete_note_nodes(self, note_path: str):
        """Delete all nodes associated with a note (on reindex)

        Deletes:
        1. Primary note node (note:path)
        2. Header nodes (note:path:h0, note:path:h1, etc.)
        3. Orphaned tags (tags with no remaining references)
        4. Orphaned placeholders (note_ref with no remaining references)

        Smart cleanup ensures shared resources (tags) are only deleted
        when no other notes reference them.
        """
        note_id = f"note:{note_path}"

        # Delete primary note node and headers (CASCADE handles edges)
        self._delete_note_and_headers(note_id)

        # Clean up orphaned shared nodes
        self.cleanup_orphan_tags()
        self.cleanup_orphan_placeholders()

    def _delete_note_and_headers(self, note_id: str):
        """Delete note node and all its header children"""
        # Headers have node_id pattern: note:path:h0, note:path:h1, etc.
        # Use LIKE pattern to catch all headers
        self.conn.execute("""
            DELETE FROM graph_nodes
            WHERE node_id = ? OR node_id LIKE ?
        """, (note_id, f"{note_id}:h%"))

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
        """Get graph statistics"""
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

    def persist_graph(self, graph_export: Dict):
        """Persist entire graph from ObsidianGraphBuilder export

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

            self.save_node(node_id, node_type, title, content, metadata)

        # Persist edges
        for edge_data in graph_export.get('edges', []):
            source = edge_data.get('source')
            target = edge_data.get('target')
            edge_type = edge_data.get('type', 'unknown')
            metadata = {k: v for k, v in edge_data.items()
                       if k not in ['source', 'target', 'type']}

            self.save_edge(source, target, edge_type, metadata)

    def commit(self):
        """Commit transaction"""
        self.conn.commit()
