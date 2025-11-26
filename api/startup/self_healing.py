"""Self-healing service for automatic database repair at startup

Performs safe, non-destructive repairs automatically:
- Delete empty documents (records with no chunks)
- Backfill missing chunk counts (historical data)

Controlled via AUTO_SELF_HEAL environment variable (default: true).
"""
import os
import sqlite3
from pathlib import Path
from typing import Dict, Any

from config import default_config


class SelfHealingService:
    """Automatic database repair at startup"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or default_config.database.path
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

        self._delete_empty_documents()
        self._backfill_chunk_counts()

        self._print_summary()
        print("=== Self-Healing Complete ===\n")

        return self._results

    def _delete_empty_documents(self):
        """Delete document records that have no chunks

        These are orphan records from interrupted processing where
        the document metadata was saved but chunks were never created.
        """
        try:
            conn = sqlite3.connect(self.db_path)

            # Find documents with no chunks
            cursor = conn.execute('''
                SELECT d.id, d.file_path
                FROM documents d
                WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
            ''')
            orphans = cursor.fetchall()

            if not orphans:
                self._results['empty_documents'] = {'found': 0, 'deleted': 0}
                return

            # Delete orphan documents and their progress records
            deleted = 0
            for doc_id, file_path in orphans:
                conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
                conn.execute('DELETE FROM processing_progress WHERE file_path = ?', (file_path,))
                deleted += 1

            conn.commit()
            conn.close()

            self._results['empty_documents'] = {
                'found': len(orphans),
                'deleted': deleted
            }

            if deleted > 0:
                print(f"  [Self-Heal] Deleted {deleted} empty document records")

        except Exception as e:
            print(f"  [Self-Heal] Warning: Failed to clean empty documents: {e}")
            self._results['empty_documents'] = {'error': str(e)}

    def _backfill_chunk_counts(self):
        """Backfill missing chunk counts for historical documents

        Documents indexed before chunk tracking may have total_chunks=0
        but actual chunks in the database. This fills in the correct counts.
        """
        try:
            # Try to import the migration module
            from migrations.backfill_chunk_counts import backfill_chunk_counts
            result = backfill_chunk_counts(dry_run=False)

            self._results['chunk_counts'] = {
                'checked': result.get('checked', 0),
                'updated': result.get('updated', 0)
            }

            if result.get('updated', 0) > 0:
                print(f"  [Self-Heal] Backfilled chunk counts for {result['updated']} documents")

        except ImportError:
            # Migration module not available - skip silently
            self._results['chunk_counts'] = {'skipped': True, 'reason': 'migration not available'}
        except Exception as e:
            print(f"  [Self-Heal] Warning: Failed to backfill chunk counts: {e}")
            self._results['chunk_counts'] = {'error': str(e)}

    def _print_summary(self):
        """Print summary of self-healing operations"""
        empty_docs = self._results.get('empty_documents', {})
        chunk_counts = self._results.get('chunk_counts', {})

        total_fixes = (
            empty_docs.get('deleted', 0) +
            chunk_counts.get('updated', 0)
        )

        if total_fixes == 0:
            print("  [Self-Heal] Database is healthy, no repairs needed")
        else:
            print(f"  [Self-Heal] Total repairs: {total_fixes}")
