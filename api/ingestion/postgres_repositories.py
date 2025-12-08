"""
PostgreSQL repository implementations for pgvector.

These repositories replace the SQLite-based repositories with PostgreSQL-compatible
implementations. Key differences:
- Uses %s placeholders instead of ?
- Uses psycopg2 cursor interface
- Vector embeddings stored as pgvector vector type
- Full-text search uses tsvector instead of FTS5
"""
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

import numpy as np

from ingestion.interfaces import (
    DocumentRepository,
    ChunkRepository,
    VectorChunkRepository,
    FTSChunkRepository,
    SearchRepository,
    GraphRepository,
)

logger = logging.getLogger(__name__)


class PostgresDocumentRepository(DocumentRepository):
    """CRUD operations for documents table (PostgreSQL version)."""

    def __init__(self, conn):
        self.conn = conn

    def add(self, path: str, hash_val: str, extraction_method: str = None) -> int:
        """Insert document record and return document ID"""
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documents (file_path, file_hash, extraction_method) VALUES (%s, %s, %s) RETURNING id",
                (path, hash_val, extraction_method)
            )
            return cur.fetchone()[0]

    def get(self, doc_id: int) -> Optional[Dict]:
        """Get document by ID"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE id = %s",
                (doc_id,)
            )
            result = cur.fetchone()
            if not result:
                return None
            return {
                'id': result[0],
                'file_path': result[1],
                'file_hash': result[2],
                'indexed_at': result[3],
                'extraction_method': result[4]
            }

    def find_by_path(self, path: str) -> Optional[Dict]:
        """Get document by file path"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_path = %s",
                (path,)
            )
            result = cur.fetchone()
            if not result:
                return None
            return {
                'id': result[0],
                'file_path': result[1],
                'file_hash': result[2],
                'indexed_at': result[3],
                'extraction_method': result[4]
            }

    def find_by_hash(self, hash_val: str) -> Optional[Dict]:
        """Get document by content hash"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents WHERE file_hash = %s",
                (hash_val,)
            )
            result = cur.fetchone()
            if not result:
                return None
            return {
                'id': result[0],
                'file_path': result[1],
                'file_hash': result[2],
                'indexed_at': result[3],
                'extraction_method': result[4]
            }

    def exists(self, path: str) -> bool:
        """Check if document exists by path"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM documents WHERE file_path = %s LIMIT 1", (path,))
            return cur.fetchone() is not None

    def hash_exists(self, hash_val: str) -> bool:
        """Check if document with this hash exists"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT 1 FROM documents WHERE file_hash = %s LIMIT 1", (hash_val,))
            return cur.fetchone() is not None

    def update_path(self, old_path: str, new_path: str):
        """Update file path (for file moves)"""
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET file_path = %s WHERE file_path = %s",
                (new_path, old_path)
            )

    def update_path_by_hash(self, hash_val: str, new_path: str):
        """Update file path by hash (for file moves)"""
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET file_path = %s WHERE file_hash = %s",
                (new_path, hash_val)
            )

    def delete(self, path: str):
        """Delete document by path (CASCADE deletes chunks)"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE file_path = %s", (path,))

    def delete_by_id(self, doc_id: int):
        """Delete document by ID (CASCADE deletes chunks)"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s", (doc_id,))

    def list_all(self) -> List[Dict]:
        """Get all documents"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, file_path, file_hash, indexed_at, extraction_method FROM documents"
            )
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'file_path': row[1],
                    'file_hash': row[2],
                    'indexed_at': row[3],
                    'extraction_method': row[4]
                })
            return results

    def count(self) -> int:
        """Count total documents"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            return cur.fetchone()[0]

    def get_extraction_method(self, path: str) -> str:
        """Get extraction method used for a document"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT extraction_method FROM documents WHERE file_path = %s",
                (path,)
            )
            result = cur.fetchone()
            return result[0] if result and result[0] else 'unknown'

    def search_by_pattern(self, pattern: str) -> List[Dict]:
        """Search documents by filename pattern"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, file_path, file_hash, indexed_at, extraction_method
                FROM documents
                WHERE file_path LIKE %s
                ORDER BY indexed_at DESC
            """, (f"%{pattern}%",))
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'file_path': row[1],
                    'file_hash': row[2],
                    'indexed_at': row[3],
                    'extraction_method': row[4]
                })
            return results


class PostgresChunkRepository(ChunkRepository):
    """CRUD operations for chunks table (PostgreSQL version)."""

    def __init__(self, conn):
        self.conn = conn

    def add(self, document_id: int, content: str, page: int = None, chunk_index: int = None) -> int:
        """Insert chunk and return chunk ID"""
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chunks (document_id, content, page, chunk_index) VALUES (%s, %s, %s, %s) RETURNING id",
                (document_id, content, page, chunk_index)
            )
            return cur.fetchone()[0]

    def get(self, chunk_id: int) -> Optional[Dict]:
        """Get chunk by ID"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, document_id, content, page, chunk_index FROM chunks WHERE id = %s",
                (chunk_id,)
            )
            result = cur.fetchone()
            if not result:
                return None
            return {
                'id': result[0],
                'document_id': result[1],
                'content': result[2],
                'page': result[3],
                'chunk_index': result[4]
            }

    def get_by_document(self, document_id: int) -> List[Dict]:
        """Get all chunks for a document"""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, document_id, content, page, chunk_index FROM chunks WHERE document_id = %s ORDER BY chunk_index",
                (document_id,)
            )
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'document_id': row[1],
                    'content': row[2],
                    'page': row[3],
                    'chunk_index': row[4]
                })
            return results

    def delete_by_document(self, document_id: int):
        """Delete all chunks for a document"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))

    def count(self) -> int:
        """Count total chunks"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            return cur.fetchone()[0]

    def count_by_document(self, document_id: int) -> int:
        """Count chunks for a specific document"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks WHERE document_id = %s", (document_id,))
            return cur.fetchone()[0]


class PostgresVectorChunkRepository(VectorChunkRepository):
    """Vector embeddings repository using pgvector (PostgreSQL version).

    Unlike vectorlite which uses a separate HNSW index file, pgvector stores
    vectors directly in the table with built-in HNSW indexing.
    """

    def __init__(self, conn):
        self.conn = conn

    def add(self, chunk_id: int, embedding: List[float]) -> None:
        """Insert vector embedding for a chunk.

        pgvector accepts Python lists directly - no need for blob conversion.
        """
        with self.conn.cursor() as cur:
            # pgvector accepts list as vector
            cur.execute(
                "INSERT INTO vec_chunks (rowid, embedding) VALUES (%s, %s)",
                (chunk_id, embedding)
            )

    def add_batch(self, chunk_ids: List[int], embeddings: List[List[float]]) -> None:
        """Batch insert vector embeddings."""
        with self.conn.cursor() as cur:
            from psycopg2.extras import execute_values
            data = [(chunk_id, emb) for chunk_id, emb in zip(chunk_ids, embeddings)]
            execute_values(
                cur,
                "INSERT INTO vec_chunks (rowid, embedding) VALUES %s",
                data,
                template="(%s, %s)"
            )

    def delete_by_chunk(self, chunk_id: int) -> None:
        """Delete vector embedding for a chunk."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM vec_chunks WHERE rowid = %s", (chunk_id,))

    def delete_by_chunks(self, chunk_ids: List[int]) -> None:
        """Delete vector embeddings for multiple chunks."""
        if not chunk_ids:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM vec_chunks WHERE rowid = ANY(%s)",
                (chunk_ids,)
            )

    def count(self) -> int:
        """Count total vector embeddings."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vec_chunks")
            return cur.fetchone()[0]


class PostgresFTSChunkRepository(FTSChunkRepository):
    """Full-text search repository using PostgreSQL tsvector.

    Replaces SQLite FTS5 with PostgreSQL's built-in full-text search.
    Uses generated tsvector column with GIN index.
    """

    def __init__(self, conn):
        self.conn = conn

    def add(self, chunk_id: int, content: str) -> None:
        """Insert FTS entry for a chunk.

        The tsvector is automatically generated by the GENERATED column.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fts_chunks (chunk_id, content) VALUES (%s, %s)",
                (chunk_id, content)
            )

    def delete_by_chunk(self, chunk_id: int) -> None:
        """Delete FTS entry for a chunk."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM fts_chunks WHERE chunk_id = %s", (chunk_id,))

    def delete_by_chunks(self, chunk_ids: List[int]) -> None:
        """Delete FTS entries for multiple chunks."""
        if not chunk_ids:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM fts_chunks WHERE chunk_id = ANY(%s)",
                (chunk_ids,)
            )

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search using PostgreSQL full-text search.

        Returns chunk_ids with relevance scores.
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT chunk_id, ts_rank(tsv, plainto_tsquery('english', %s)) AS rank
                FROM fts_chunks
                WHERE tsv @@ plainto_tsquery('english', %s)
                ORDER BY rank DESC
                LIMIT %s
            """, (query, query, limit))
            results = []
            for row in cur.fetchall():
                results.append({
                    'chunk_id': row[0],
                    'rank': row[1]
                })
            return results

    def count(self) -> int:
        """Count total FTS entries."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fts_chunks")
            return cur.fetchone()[0]


class PostgresSearchRepository(SearchRepository):
    """Vector similarity search using pgvector (PostgreSQL version).

    Uses pgvector's <=> operator for cosine distance.
    HNSW index provides approximate nearest neighbor search.
    """

    def __init__(self, conn):
        self.conn = conn

    def vector_search(self, embedding: List[float], top_k: int,
                      threshold: float = None) -> List[Dict]:
        """Search for similar vectors using pgvector HNSW.

        Args:
            embedding: Query vector
            top_k: Number of results to return
            threshold: Optional similarity threshold (0-1, higher = more similar)

        Returns:
            List of dicts with chunk content, file_path, score, etc.
        """
        results = self._execute_vector_search(embedding, top_k)
        return self._format_results(results, threshold)

    def _execute_vector_search(self, embedding: List[float], top_k: int) -> List[tuple]:
        """Execute pgvector similarity search.

        pgvector <=> operator returns cosine distance (0 = identical, 2 = opposite).
        We convert to similarity score: 1 - (distance / 2) for 0-1 range.
        """
        with self.conn.cursor() as cur:
            # Get vector results with distances
            cur.execute("""
                SELECT v.rowid, (v.embedding <=> %s::vector) AS distance
                FROM vec_chunks v
                ORDER BY v.embedding <=> %s::vector
                LIMIT %s
            """, (embedding, embedding, top_k))
            vector_results = cur.fetchall()

            if not vector_results:
                return []

            # Get chunk metadata
            chunk_ids = [r[0] for r in vector_results]
            distances = {r[0]: r[1] for r in vector_results}

            placeholders = ','.join(['%s'] * len(chunk_ids))
            cur.execute(f"""
                SELECT c.id, c.content, d.file_path, c.page
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.id IN ({placeholders})
            """, chunk_ids)

            chunk_data = {row[0]: row for row in cur.fetchall()}

            # Combine results preserving order
            results = []
            for chunk_id in chunk_ids:
                if chunk_id in chunk_data:
                    row = chunk_data[chunk_id]
                    distance = distances[chunk_id]
                    # Convert cosine distance to similarity (0-1 scale)
                    similarity = 1 - (distance / 2)
                    results.append((row[0], row[1], row[2], row[3], similarity))

            return results

    def _format_results(self, results: List[tuple], threshold: float = None) -> List[Dict]:
        """Format search results into response dicts."""
        formatted = []
        for row in results:
            chunk_id, content, file_path, page, score = row

            # Apply threshold filter
            if threshold is not None and score < threshold:
                continue

            formatted.append({
                'chunk_id': chunk_id,
                'content': content,
                'file_path': file_path,
                'page': page,
                'score': score,
                'source': Path(file_path).name if file_path else None,  # For QueryExecutor compatibility
                'filename': Path(file_path).name if file_path else None  # Legacy alias
            })

        return formatted


class PostgresGraphRepository(GraphRepository):
    """Knowledge graph repository (PostgreSQL version)."""

    def __init__(self, conn):
        self.conn = conn

    def add_node(self, node_id: str, node_type: str, title: str,
                 content: str = None, metadata: str = None) -> None:
        """Add or update a graph node."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO graph_nodes (node_id, node_type, title, content, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (node_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata
            """, (node_id, node_type, title, content, metadata))

    def add_edge(self, source_id: str, target_id: str, edge_type: str,
                 metadata: str = None) -> None:
        """Add an edge between nodes."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO graph_edges (source_id, target_id, edge_type, metadata)
                VALUES (%s, %s, %s, %s)
            """, (source_id, target_id, edge_type, metadata))

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a node by ID."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT node_id, node_type, title, content, metadata, created_at
                FROM graph_nodes WHERE node_id = %s
            """, (node_id,))
            result = cur.fetchone()
            if not result:
                return None
            return {
                'node_id': result[0],
                'node_type': result[1],
                'title': result[2],
                'content': result[3],
                'metadata': result[4],
                'created_at': result[5]
            }

    def get_edges_from(self, source_id: str) -> List[Dict]:
        """Get all edges from a source node."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, source_id, target_id, edge_type, metadata
                FROM graph_edges WHERE source_id = %s
            """, (source_id,))
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'source_id': row[1],
                    'target_id': row[2],
                    'edge_type': row[3],
                    'metadata': row[4]
                })
            return results

    def get_edges_to(self, target_id: str) -> List[Dict]:
        """Get all edges to a target node."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, source_id, target_id, edge_type, metadata
                FROM graph_edges WHERE target_id = %s
            """, (target_id,))
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'source_id': row[1],
                    'target_id': row[2],
                    'edge_type': row[3],
                    'metadata': row[4]
                })
            return results

    def delete_node(self, node_id: str) -> None:
        """Delete a node and its edges (CASCADE)."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM graph_nodes WHERE node_id = %s", (node_id,))

    def delete_note_nodes(self, file_path: str) -> None:
        """Delete all nodes associated with a file path."""
        # Node IDs for notes are typically based on file path
        node_id = f"note:{Path(file_path).stem}"
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM graph_nodes WHERE node_id = %s", (node_id,))

    def update_note_path(self, old_path: str, new_path: str) -> None:
        """Update node IDs when a file is moved."""
        old_node_id = f"note:{Path(old_path).stem}"
        new_node_id = f"note:{Path(new_path).stem}"
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE graph_nodes SET node_id = %s WHERE node_id = %s",
                (new_node_id, old_node_id)
            )

    def link_chunk_to_node(self, chunk_id: int, node_id: str, link_type: str = 'primary') -> None:
        """Link a chunk to a graph node."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chunk_graph_links (chunk_id, node_id, link_type)
                VALUES (%s, %s, %s)
            """, (chunk_id, node_id, link_type))

    def get_chunks_for_node(self, node_id: str) -> List[int]:
        """Get all chunk IDs linked to a node."""
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id FROM chunk_graph_links WHERE node_id = %s",
                (node_id,)
            )
            return [row[0] for row in cur.fetchall()]

    def persist_graph(self, graph_export: Dict) -> None:
        """Persist entire graph from ObsidianGraphBuilder export.

        Args:
            graph_export: Dictionary from ObsidianGraphBuilder.export_graph()
                         with 'nodes' and 'edges' keys
        """
        if not graph_export:
            return

        nodes = graph_export.get('nodes', [])
        edges = graph_export.get('edges', [])

        for node_data in nodes:
            node_id = node_data.get('id')
            node_type = node_data.get('node_type', 'unknown')
            title = node_data.get('title', '')
            content = node_data.get('content')
            # Extract metadata by excluding core fields
            excluded = {'id', 'node_type', 'title', 'content'}
            metadata = {k: v for k, v in node_data.items() if k not in excluded}
            import json
            self.add_node(node_id, node_type, title, content, json.dumps(metadata) if metadata else None)

        for edge_data in edges:
            source = edge_data.get('source')
            target = edge_data.get('target')
            edge_type = edge_data.get('type', 'unknown')
            excluded = {'source', 'target', 'type'}
            metadata = {k: v for k, v in edge_data.items() if k not in excluded}
            import json
            self.add_edge(source, target, edge_type, json.dumps(metadata) if metadata else None)

    def commit(self) -> None:
        """Commit transaction."""
        self.conn.commit()

    def cleanup_orphan_tags(self) -> None:
        """Delete tag nodes that have no incoming edges."""
        with self.conn.cursor() as cur:
            cur.execute("""
                DELETE FROM graph_nodes
                WHERE node_type = 'tag'
                AND node_id NOT IN (
                    SELECT DISTINCT target_id
                    FROM graph_edges
                    WHERE edge_type = 'tag'
                )
            """)

    def cleanup_orphan_placeholders(self) -> None:
        """Delete placeholder nodes (note_ref) with no incoming edges."""
        with self.conn.cursor() as cur:
            cur.execute("""
                DELETE FROM graph_nodes
                WHERE node_type = 'note_ref'
                AND node_id NOT IN (
                    SELECT DISTINCT target_id
                    FROM graph_edges
                    WHERE edge_type = 'wikilink'
                )
            """)

    def clear_graph(self) -> None:
        """Clear all graph data (for reindexing)."""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM chunk_graph_links")
            cur.execute("DELETE FROM graph_metadata")
            cur.execute("DELETE FROM graph_edges")
            cur.execute("DELETE FROM graph_nodes")

    def get_graph_stats(self) -> Dict:
        """Get graph statistics."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY node_type")
            nodes_by_type = dict(cur.fetchall())

            cur.execute("SELECT edge_type, COUNT(*) FROM graph_edges GROUP BY edge_type")
            edges_by_type = dict(cur.fetchall())

            cur.execute("SELECT COUNT(*) FROM graph_nodes")
            total_nodes = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM graph_edges")
            total_edges = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM chunk_graph_links")
            total_chunk_links = cur.fetchone()[0]

            return {
                'nodes_by_type': nodes_by_type,
                'edges_by_type': edges_by_type,
                'total_nodes': total_nodes,
                'total_edges': total_edges,
                'total_chunk_links': total_chunk_links
            }
