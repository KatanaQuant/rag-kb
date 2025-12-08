"""
PostgreSQL maintenance utilities.

Simplified maintenance operations for PostgreSQL + pgvector.
Many SQLite/vectorlite-specific operations are no longer needed.
"""
import logging
from typing import Dict, List, Optional
from pathlib import Path

from ingestion.database_factory import DatabaseFactory
from config import default_config

logger = logging.getLogger(__name__)


class PostgresIntegrityChecker:
    """Database integrity checker for PostgreSQL.

    PostgreSQL handles most integrity via constraints (FK, UNIQUE).
    This checker verifies application-level consistency.
    """

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = DatabaseFactory.create_connection(config)
        self.conn = None

    def connect(self):
        self.conn = self.db_conn.connect()

    def close(self):
        self.db_conn.close()

    def check_all(self) -> Dict:
        """Run all integrity checks."""
        if not self.conn:
            self.connect()

        results = {
            'orphan_chunks': self.check_orphan_chunks(),
            'orphan_vectors': self.check_orphan_vectors(),
            'orphan_fts': self.check_orphan_fts(),
            'missing_files': self.check_missing_files(),
            'vector_count_mismatch': self.check_vector_count_mismatch(),
        }

        results['all_passed'] = all(
            r.get('ok', True) for r in results.values()
        )
        return results

    def check_orphan_chunks(self) -> Dict:
        """Check for chunks without documents (shouldn't exist due to CASCADE)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM chunks c
                WHERE NOT EXISTS (
                    SELECT 1 FROM documents d WHERE d.id = c.document_id
                )
            """)
            count = cur.fetchone()[0]
        return {'ok': count == 0, 'orphan_count': count}

    def check_orphan_vectors(self) -> Dict:
        """Check for vectors without chunks."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM vec_chunks v
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunks c WHERE c.id = v.rowid
                )
            """)
            count = cur.fetchone()[0]
        return {'ok': count == 0, 'orphan_count': count}

    def check_orphan_fts(self) -> Dict:
        """Check for FTS entries without chunks."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM fts_chunks f
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunks c WHERE c.id = f.chunk_id
                )
            """)
            count = cur.fetchone()[0]
        return {'ok': count == 0, 'orphan_count': count}

    def check_missing_files(self) -> Dict:
        """Check for documents where the source file no longer exists."""
        missing = []
        with self.conn.cursor() as cur:
            cur.execute("SELECT file_path FROM documents")
            for row in cur.fetchall():
                file_path = row[0]
                if not Path(file_path).exists():
                    missing.append(file_path)
        return {'ok': len(missing) == 0, 'missing_files': missing[:20]}

    def check_vector_count_mismatch(self) -> Dict:
        """Check if vector count matches chunk count."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM vec_chunks")
            vector_count = cur.fetchone()[0]
        return {
            'ok': chunk_count == vector_count,
            'chunk_count': chunk_count,
            'vector_count': vector_count
        }


class PostgresOrphanCleaner:
    """Cleans up orphan records in PostgreSQL.

    Most orphans are prevented by CASCADE constraints, but this handles
    edge cases and provides a manual cleanup option.
    """

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = DatabaseFactory.create_connection(config)
        self.conn = None

    def connect(self):
        self.conn = self.db_conn.connect()

    def close(self):
        self.db_conn.close()

    def clean_all(self, dry_run: bool = True) -> Dict:
        """Clean all orphan records."""
        if not self.conn:
            self.connect()

        results = {
            'orphan_vectors': self.clean_orphan_vectors(dry_run),
            'orphan_fts': self.clean_orphan_fts(dry_run),
            'orphan_graph_nodes': self.clean_orphan_graph_nodes(dry_run),
            'missing_file_documents': self.clean_missing_file_documents(dry_run),
            'dry_run': dry_run
        }
        return results

    def clean_orphan_vectors(self, dry_run: bool) -> Dict:
        """Delete vectors without corresponding chunks."""
        with self.conn.cursor() as cur:
            if dry_run:
                cur.execute("""
                    SELECT COUNT(*) FROM vec_chunks v
                    WHERE NOT EXISTS (
                        SELECT 1 FROM chunks c WHERE c.id = v.rowid
                    )
                """)
                count = cur.fetchone()[0]
            else:
                cur.execute("""
                    DELETE FROM vec_chunks v
                    WHERE NOT EXISTS (
                        SELECT 1 FROM chunks c WHERE c.id = v.rowid
                    )
                """)
                count = cur.rowcount
                self.conn.commit()
        return {'deleted': count}

    def clean_orphan_fts(self, dry_run: bool) -> Dict:
        """Delete FTS entries without corresponding chunks."""
        with self.conn.cursor() as cur:
            if dry_run:
                cur.execute("""
                    SELECT COUNT(*) FROM fts_chunks f
                    WHERE NOT EXISTS (
                        SELECT 1 FROM chunks c WHERE c.id = f.chunk_id
                    )
                """)
                count = cur.fetchone()[0]
            else:
                cur.execute("""
                    DELETE FROM fts_chunks f
                    WHERE NOT EXISTS (
                        SELECT 1 FROM chunks c WHERE c.id = f.chunk_id
                    )
                """)
                count = cur.rowcount
                self.conn.commit()
        return {'deleted': count}

    def clean_orphan_graph_nodes(self, dry_run: bool) -> Dict:
        """Delete orphan graph nodes (tags/placeholders with no edges)."""
        with self.conn.cursor() as cur:
            if dry_run:
                cur.execute("""
                    SELECT COUNT(*) FROM graph_nodes
                    WHERE node_type IN ('tag', 'note_ref')
                    AND node_id NOT IN (
                        SELECT DISTINCT target_id FROM graph_edges
                    )
                """)
                count = cur.fetchone()[0]
            else:
                cur.execute("""
                    DELETE FROM graph_nodes
                    WHERE node_type IN ('tag', 'note_ref')
                    AND node_id NOT IN (
                        SELECT DISTINCT target_id FROM graph_edges
                    )
                """)
                count = cur.rowcount
                self.conn.commit()
        return {'deleted': count}

    def clean_missing_file_documents(self, dry_run: bool) -> Dict:
        """Delete documents where the source file no longer exists."""
        missing = []
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, file_path FROM documents")
            for row in cur.fetchall():
                doc_id, file_path = row
                if not Path(file_path).exists():
                    missing.append(doc_id)

        if not dry_run and missing:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM documents WHERE id = ANY(%s)",
                    (missing,)
                )
                self.conn.commit()

        return {'deleted': len(missing), 'file_paths': missing[:10]}


class PostgresStatsCollector:
    """Collects database statistics for PostgreSQL."""

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = DatabaseFactory.create_connection(config)
        self.conn = None

    def connect(self):
        self.conn = self.db_conn.connect()

    def close(self):
        self.db_conn.close()

    def get_stats(self) -> Dict:
        """Get comprehensive database statistics."""
        if not self.conn:
            self.connect()

        return {
            'documents': self._get_document_stats(),
            'chunks': self._get_chunk_stats(),
            'vectors': self._get_vector_stats(),
            'fts': self._get_fts_stats(),
            'graph': self._get_graph_stats(),
            'storage': self._get_storage_stats(),
        }

    def _get_document_stats(self) -> Dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents")
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT extraction_method, COUNT(*)
                FROM documents
                GROUP BY extraction_method
            """)
            by_method = dict(cur.fetchall())
        return {'total': total, 'by_extraction_method': by_method}

    def _get_chunk_stats(self) -> Dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks")
            total = cur.fetchone()[0]
            cur.execute("SELECT AVG(LENGTH(content)) FROM chunks")
            avg_length = cur.fetchone()[0]
        return {'total': total, 'avg_content_length': avg_length}

    def _get_vector_stats(self) -> Dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM vec_chunks")
            total = cur.fetchone()[0]
        return {'total': total, 'embedding_dim': self.config.embedding_dim}

    def _get_fts_stats(self) -> Dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fts_chunks")
            total = cur.fetchone()[0]
        return {'total': total}

    def _get_graph_stats(self) -> Dict:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM graph_nodes")
            nodes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM graph_edges")
            edges = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM chunk_graph_links")
            links = cur.fetchone()[0]
        return {'nodes': nodes, 'edges': edges, 'chunk_links': links}

    def _get_storage_stats(self) -> Dict:
        """Get PostgreSQL storage statistics."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT relname, pg_total_relation_size(relid) as size
                FROM pg_stat_user_tables
                WHERE schemaname = 'public'
                ORDER BY size DESC
            """)
            tables = {row[0]: row[1] for row in cur.fetchall()}
        total = sum(tables.values())
        return {'total_bytes': total, 'tables': tables}
