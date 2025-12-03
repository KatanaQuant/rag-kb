from pathlib import Path


class OrphanDetector:
    """Detects and repairs orphaned files (processed but not embedded)"""

    def __init__(self, progress_tracker, vector_store):
        self.tracker = progress_tracker
        self.store = vector_store

    def detect_orphans(self):
        """Detect orphaned files"""
        if not self.tracker:
            return []

        import sqlite3
        conn = sqlite3.connect(self.tracker.get_db_path())
        cursor = conn.execute('''
            SELECT pp.file_path, pp.chunks_processed, pp.last_updated
            FROM processing_progress pp
            LEFT JOIN documents d ON pp.file_path = d.file_path
            WHERE pp.status = 'completed' AND d.id IS NULL
            ORDER BY pp.last_updated DESC
        ''')
        orphans = [{'path': row[0], 'chunks': row[1], 'updated': row[2]} for row in cursor.fetchall()]
        conn.close()
        return orphans

    def repair_orphans(self, queue):
        """Repair orphaned files by adding them to queue with HIGH priority"""
        from pipeline.indexing_queue import Priority

        orphans = self.detect_orphans()
        if not orphans:
            return 0
        self._print_header(orphans)
        stats = self._add_to_queue(orphans, queue)
        self._print_summary(stats)
        return stats['queued']

    def _print_header(self, orphans):
        """Print repair header and sample"""
        print(f"\n{'='*80}")
        print(f"Found {len(orphans)} orphaned files (processed but not embedded)")
        print(f"{'='*80}")
        print("\nSample orphaned files:")
        for orphan in orphans[:5]:
            filename = orphan['path'].split('/')[-1]
            print(f"  - {filename} ({orphan['updated']})")
        if len(orphans) > 5:
            print(f"  ... and {len(orphans) - 5} more\n")
        print("Repairing orphaned files...")

    def _add_to_queue(self, orphans, queue):
        """Add all orphaned files to queue with HIGH priority"""
        stats = {'queued': 0, 'non_existent': 0}
        for idx, orphan in enumerate(orphans):
            self._show_progress(idx, len(orphans), stats)
            self._queue_one(orphan, queue, stats)
        return stats

    def _show_progress(self, idx, total, stats):
        """Show progress every 50 files"""
        if self._is_progress_milestone(idx):
            self._print_progress(idx, total, stats)

    def _is_progress_milestone(self, idx):
        """Check if should show progress"""
        return idx > 0 and idx % 50 == 0

    def _print_progress(self, idx, total, stats):
        """Print progress message"""
        print(f"Orphan repair progress: {idx}/{total} "
              f"({stats['queued']} queued, {stats['non_existent']} non-existent)")

    def _queue_one(self, orphan, queue, stats):
        """Queue one orphaned file for reindexing"""
        from pathlib import Path
        from pipeline.indexing_queue import Priority

        try:
            path = Path(orphan['path'])
            if not path.exists():
                self._handle_non_existent(orphan, stats)
                return

            # Check if this is a converted EPUB (moved to original/)
            if self._is_converted_epub(path):
                self._handle_converted_epub(orphan, stats)
                return

            # Delete from tracker so it can be reprocessed
            self.tracker.delete_document(str(path))

            # Add to queue with HIGH priority (orphans process before normal files)
            queue.add(path, priority=Priority.HIGH, force=True)
            stats['queued'] += 1

        except Exception as e:
            print(f"ERROR queuing {orphan['path'].split('/')[-1]}: {e}")

    def _is_converted_epub(self, path: Path) -> bool:
        """Check if this is an EPUB that was converted to PDF

        EPUBs are converted to PDF and moved to original/ subdirectory.
        The PDF is indexed instead, so the EPUB progress entry is stale.

        Works for both cases:
        - Case 1: EPUB already in original/ - PDF is in parent directory
        - Case 2: EPUB at original location - original/ copy and PDF exist
        """
        if path.suffix.lower() != '.epub':
            return False

        # Case 1: EPUB is already in original/ directory
        # Check if PDF exists in parent directory
        if path.parent.name == 'original':
            pdf_path = path.parent.parent / path.with_suffix('.pdf').name
            return pdf_path.exists()

        # Case 2: EPUB at original location (database has old path)
        # Check if EPUB was moved to original/ and PDF exists
        original_path = path.parent / 'original' / path.name
        pdf_path = path.with_suffix('.pdf')

        return original_path.exists() and pdf_path.exists()

    def _handle_converted_epub(self, orphan, stats):
        """Handle converted EPUB - clean up progress entry"""
        self.tracker.delete_document(orphan['path'])
        if 'epub_converted' not in stats:
            stats['epub_converted'] = 0
        stats['epub_converted'] += 1

    def _handle_non_existent(self, orphan, stats):
        """Handle non-existent orphan files

        Checks if file was a converted EPUB before marking as non-existent.
        """
        path = Path(orphan['path'])

        # Check if this was a converted EPUB (moved to original/)
        if self._is_converted_epub(path):
            self._handle_converted_epub(orphan, stats)
            return

        self.tracker.delete_document(orphan['path'])
        stats['non_existent'] += 1

    def _print_summary(self, stats):
        """Print repair summary"""
        if stats.get('epub_converted', 0) > 0:
            print(f"\nConverted EPUBs cleaned: {stats['epub_converted']}")
        print(f"Non-existent files cleaned: {stats['non_existent']}")
        print(f"\n{'='*80}")
        print(f"Orphan repair complete: {stats['queued']} files queued for reindexing")
        print(f"{'='*80}\n")

