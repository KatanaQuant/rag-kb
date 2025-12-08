"""PostgreSQL self-healing service for automatic database repair at startup

Performs safe, non-destructive repairs automatically:
- Delete empty documents (records with no chunks)
- Verify vector/FTS consistency

Controlled via AUTO_SELF_HEAL environment variable (default: true).
"""
import os
from typing import Dict, Any

from config import default_config
from ingestion.database_factory import DatabaseFactory


class PostgresSelfHealingService:
    """Automatic database repair at startup for PostgreSQL"""

    def __init__(self, config=default_config.database):
        self.config = config
        self._results: Dict[str, Any] = {}

    def is_enabled(self) -> bool:
        """Check if self-healing is enabled via environment variable"""
        return os.getenv('AUTO_SELF_HEAL', 'true').lower() == 'true'

    def run(self) -> Dict[str, Any]:
        """Run all self-healing operations

        Returns:
            Summary of all repairs performed
        """
        if not self.is_enabled():
            print("Self-healing disabled (AUTO_SELF_HEAL=false)")
            return {'enabled': False}

        print("\n=== Starting Self-Healing Stage ===")

        db = DatabaseFactory.create_connection(self.config)
        conn = db.connect()

        try:
            self._delete_empty_documents(conn)
            self._verify_consistency(conn)
        finally:
            db.close()

        self._print_summary()
        print("=== Self-Healing Complete ===\n")

        return self._results

    def _delete_empty_documents(self, conn):
        """Delete document records that have no chunks

        These are orphan records from interrupted processing where
        the document metadata was saved but chunks were never created.
        """
        try:
            with conn.cursor() as cur:
                # Find documents with no chunks
                cur.execute('''
                    SELECT d.id, d.file_path
                    FROM documents d
                    WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
                ''')
                orphans = cur.fetchall()

            if not orphans:
                self._results['empty_documents'] = {'found': 0, 'deleted': 0}
                return

            # Delete orphan documents and their progress records
            deleted = 0
            with conn.cursor() as cur:
                for doc_id, file_path in orphans:
                    cur.execute('DELETE FROM documents WHERE id = %s', (doc_id,))
                    cur.execute('DELETE FROM processing_progress WHERE file_path = %s', (file_path,))
                    deleted += 1
            conn.commit()

            print(f"[Self-Heal] Deleted {deleted} empty documents")
            self._results['empty_documents'] = {'found': len(orphans), 'deleted': deleted}

        except Exception as e:
            print(f"[Self-Heal] Empty document cleanup failed: {e}")
            conn.rollback()
            self._results['empty_documents'] = {'error': str(e)}

    def _verify_consistency(self, conn):
        """Verify vector and FTS consistency"""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM vec_chunks")
                vector_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM fts_chunks")
                fts_count = cur.fetchone()[0]

            self._results['consistency'] = {
                'chunks': chunk_count,
                'vectors': vector_count,
                'fts': fts_count,
                'vectors_missing': chunk_count - vector_count,
                'fts_missing': chunk_count - fts_count
            }

            if chunk_count != vector_count:
                print(f"[Self-Heal] WARNING: {chunk_count - vector_count} chunks missing embeddings")
                print("[Self-Heal] Fix: POST /api/maintenance/rebuild-embeddings")

            if chunk_count != fts_count:
                print(f"[Self-Heal] WARNING: {chunk_count - fts_count} chunks missing FTS entries")

        except Exception as e:
            print(f"[Self-Heal] Consistency check failed: {e}")
            self._results['consistency'] = {'error': str(e)}

    def _print_summary(self):
        """Print summary of self-healing operations"""
        print("\nSelf-Healing Summary:")
        for op, result in self._results.items():
            if isinstance(result, dict):
                if 'error' in result:
                    print(f"  {op}: ERROR - {result['error']}")
                elif 'found' in result:
                    print(f"  {op}: {result.get('deleted', 0)} deleted of {result['found']} found")
                elif 'vectors_missing' in result:
                    if result['vectors_missing'] > 0 or result['fts_missing'] > 0:
                        print(f"  {op}: {result['vectors_missing']} vectors, {result['fts_missing']} FTS missing")
                    else:
                        print(f"  {op}: OK ({result['chunks']} chunks)")


# Alias for compatibility with existing imports
SelfHealingService = PostgresSelfHealingService
