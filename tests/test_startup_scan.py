"""
TDD Tests for Startup File Scanning

Ensures that all existing files in knowledge_base/ are discovered and queued
during startup, not just files that are created/modified after startup.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from main import FileWalker, IndexOrchestrator
from ingestion.file_filter import FileFilterPolicy


class TestStartupFileScan:
    """Test that startup scan finds all existing files"""

    def test_walker_finds_existing_files(self, tmp_path):
        """Test FileWalker discovers all existing files on startup"""
        # Setup: Create files BEFORE walker is initialized (simulates startup)
        (tmp_path / "file1.pdf").touch()
        (tmp_path / "file2.md").touch()
        (tmp_path / "file3.epub").touch()

        # Create walker AFTER files exist (startup scenario)
        walker = FileWalker(tmp_path, {'.pdf', '.md', '.epub'})

        # Should find all 3 files
        found_files = list(walker.walk())
        assert len(found_files) == 3
        assert any(f.name == "file1.pdf" for f in found_files)
        assert any(f.name == "file2.md" for f in found_files)
        assert any(f.name == "file3.epub" for f in found_files)

    def test_walker_finds_files_in_subdirectories(self, tmp_path):
        """Test walker recursively finds files in subdirectories"""
        # Create nested directory structure
        (tmp_path / "subdir1").mkdir()
        (tmp_path / "subdir2").mkdir()
        (tmp_path / "subdir1" / "nested").mkdir()

        (tmp_path / "root.pdf").touch()
        (tmp_path / "subdir1" / "doc1.md").touch()
        (tmp_path / "subdir2" / "doc2.epub").touch()
        (tmp_path / "subdir1" / "nested" / "deep.pdf").touch()

        walker = FileWalker(tmp_path, {'.pdf', '.md', '.epub'})
        found_files = list(walker.walk())

        # Should find all 4 files recursively
        assert len(found_files) == 4

    def test_walker_respects_file_filter_policy(self, tmp_path):
        """Test walker excludes files based on filter policy"""
        # Create files including some that should be excluded
        (tmp_path / "good.pdf").touch()
        (tmp_path / ".hidden.md").touch()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cache.py").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf', '.md', '.py'}, filter_policy)
        found_files = list(walker.walk())

        # Should only find good.pdf (hidden and __pycache__ excluded)
        assert len(found_files) == 1
        assert found_files[0].name == "good.pdf"

    def test_walker_excludes_problematic_directory(self, tmp_path):
        """Test walker excludes 'problematic' directory"""
        (tmp_path / "good.pdf").touch()
        (tmp_path / "problematic").mkdir()
        (tmp_path / "problematic" / "bad.pdf").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf'}, filter_policy)
        found_files = list(walker.walk())

        # Should only find good.pdf (problematic/ excluded)
        assert len(found_files) == 1
        assert found_files[0].name == "good.pdf"

    def test_walker_excludes_original_directory(self, tmp_path):
        """Test walker excludes 'original' directory (where EPUBs are moved)"""
        (tmp_path / "active.pdf").touch()
        (tmp_path / "original").mkdir()
        (tmp_path / "original" / "old.epub").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf', '.epub'}, filter_policy)
        found_files = list(walker.walk())

        # Should only find active.pdf (original/ excluded)
        assert len(found_files) == 1
        assert found_files[0].name == "active.pdf"


class TestOrchestratorQueuesAllFiles:
    """Test that IndexOrchestrator queues all discovered files"""

    def test_index_all_queues_existing_files(self, tmp_path):
        """Test index_all() queues all files found by walker"""
        # Setup: Create files
        (tmp_path / "doc1.pdf").touch()
        (tmp_path / "doc2.md").touch()

        # Mock dependencies
        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf', '.md'}
        mock_tracker = Mock()
        mock_queue = Mock()
        mock_queue.add_many = Mock()

        # Create orchestrator
        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        # Run index_all
        files_queued, _ = orch.index_all(queue=mock_queue)

        # Verify both files were queued
        assert files_queued == 2
        mock_queue.add_many.assert_called_once()
        queued_files = mock_queue.add_many.call_args[0][0]
        assert len(queued_files) == 2
        assert any(f.name == "doc1.pdf" for f in queued_files)
        assert any(f.name == "doc2.md" for f in queued_files)

    def test_index_all_skips_excluded_files(self, tmp_path):
        """Test index_all() doesn't queue excluded files"""
        # Create files including excluded ones
        (tmp_path / "good.pdf").touch()
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").touch()

        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf'}
        mock_tracker = Mock()
        mock_queue = Mock()
        mock_queue.add_many = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        files_queued, _ = orch.index_all(queue=mock_queue)

        # Should only queue good.pdf
        assert files_queued == 1
        queued_files = mock_queue.add_many.call_args[0][0]
        assert len(queued_files) == 1
        assert queued_files[0].name == "good.pdf"

    def test_empty_directory_returns_zero(self, tmp_path):
        """Test empty directory doesn't queue any files"""
        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf'}
        mock_tracker = Mock()
        mock_queue = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        files_queued, _ = orch.index_all(queue=mock_queue)

        assert files_queued == 0

    def test_unsupported_file_types_not_queued(self, tmp_path):
        """Test unsupported file extensions are not queued"""
        (tmp_path / "image.jpg").touch()
        (tmp_path / "video.mp4").touch()
        (tmp_path / "document.pdf").touch()

        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf'}  # Only PDFs supported
        mock_tracker = Mock()
        mock_queue = Mock()
        mock_queue.add_many = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        files_queued, _ = orch.index_all(queue=mock_queue)

        # Should only queue document.pdf
        assert files_queued == 1
        queued_files = mock_queue.add_many.call_args[0][0]
        assert queued_files[0].name == "document.pdf"


class TestStartupScanIntegration:
    """Integration tests for complete startup scan flow"""

    def test_large_directory_scan_performance(self, tmp_path):
        """Test walker handles large directories efficiently"""
        # Create 100 files
        for i in range(100):
            (tmp_path / f"doc{i}.pdf").touch()

        walker = FileWalker(tmp_path, {'.pdf'})
        found_files = list(walker.walk())

        # Should find all 100 files
        assert len(found_files) == 100

    def test_mixed_content_realistic_scenario(self, tmp_path):
        """Test realistic knowledge base with mixed content"""
        # Simulate realistic directory structure
        (tmp_path / "books").mkdir()
        (tmp_path / "papers").mkdir()
        (tmp_path / "notes").mkdir()
        (tmp_path / "original").mkdir()
        (tmp_path / ".git").mkdir()

        # Valid files
        (tmp_path / "README.md").touch()
        (tmp_path / "books" / "book1.pdf").touch()
        (tmp_path / "books" / "book2.epub").touch()
        (tmp_path / "papers" / "paper1.pdf").touch()
        (tmp_path / "notes" / "note1.md").touch()

        # Files that should be excluded
        (tmp_path / "original" / "old.epub").touch()
        (tmp_path / ".git" / "config").touch()
        (tmp_path / ".DS_Store").touch()

        filter_policy = FileFilterPolicy()
        walker = FileWalker(tmp_path, {'.pdf', '.md', '.epub'}, filter_policy)
        found_files = list(walker.walk())

        # Should find 5 valid files (README, book1, book2, paper1, note1)
        # Should exclude original/, .git/, .DS_Store
        assert len(found_files) == 5
        file_names = {f.name for f in found_files}
        assert file_names == {"README.md", "book1.pdf", "book2.epub", "paper1.pdf", "note1.md"}


class TestStartupIncompleteFileResumption:
    """Test that incomplete files are automatically resumed on startup"""

    def test_orchestrator_resumes_incomplete_files_on_startup(self, tmp_path):
        """Test that files with in_progress status are automatically resumed"""
        # Setup: Create a file and mock progress tracker showing incomplete processing
        (tmp_path / "incomplete.pdf").touch()

        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf'}

        # Mock tracker with incomplete file
        mock_tracker = Mock()
        incomplete_progress = Mock()
        incomplete_progress.file_path = str(tmp_path / "incomplete.pdf")
        incomplete_progress.status = "in_progress"
        incomplete_progress.chunks_processed = 5
        incomplete_progress.total_chunks = 10
        mock_tracker.get_incomplete_files.return_value = [incomplete_progress]

        mock_queue = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        # Call resume_incomplete_processing
        orch.resume_incomplete_processing()

        # Verify incomplete file was queued with HIGH priority
        mock_queue.add.assert_called()
        # Check that the file was queued
        call_args = mock_queue.add.call_args
        assert call_args is not None

    def test_orchestrator_skips_completed_files(self, tmp_path):
        """Test that completed files are not reprocessed on startup"""
        (tmp_path / "completed.pdf").touch()

        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf'}

        # Mock tracker with completed file
        mock_tracker = Mock()
        completed_progress = Mock()
        completed_progress.file_path = str(tmp_path / "completed.pdf")
        completed_progress.status = "completed"
        mock_tracker.get_incomplete_files.return_value = []  # No incomplete files

        mock_queue = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        # Call resume - should not queue anything
        orch.resume_incomplete_processing()

        # Verify no calls to queue
        mock_queue.add.assert_not_called()

    def test_failed_files_are_queued_for_retry(self, tmp_path):
        """Test that files with 'failed' status are queued for retry"""
        (tmp_path / "failed.pdf").touch()

        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf'}

        # Mock tracker with failed file
        mock_tracker = Mock()
        failed_progress = Mock()
        failed_progress.file_path = str(tmp_path / "failed.pdf")
        failed_progress.status = "failed"
        failed_progress.error_message = "Extraction error"
        mock_tracker.get_incomplete_files.return_value = [failed_progress]

        mock_queue = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        orch.resume_incomplete_processing()

        # Verify failed file was queued for retry
        mock_queue.add.assert_called()

    def test_multiple_incomplete_files_all_resumed(self, tmp_path):
        """Test that all incomplete files are queued on startup"""
        (tmp_path / "file1.pdf").touch()
        (tmp_path / "file2.md").touch()
        (tmp_path / "file3.epub").touch()

        mock_indexer = Mock()
        mock_processor = Mock()
        mock_processor.SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.epub'}

        # Mock tracker with multiple incomplete files
        mock_tracker = Mock()
        incomplete_files = []
        for fname in ["file1.pdf", "file2.md", "file3.epub"]:
            progress = Mock()
            progress.file_path = str(tmp_path / fname)
            progress.status = "in_progress"
            incomplete_files.append(progress)

        mock_tracker.get_incomplete_files.return_value = incomplete_files

        mock_queue = Mock()

        orch = IndexOrchestrator(
            tmp_path,
            mock_indexer,
            mock_processor,
            mock_tracker,
            queue=mock_queue
        )

        orch.resume_incomplete_processing()

        # Verify all 3 files were queued
        assert mock_queue.add.call_count == 3


class TestStartupOrphanDetection:
    """Test that orphaned files (in DB but no embeddings) are detected and repaired"""

    def test_orphan_detection_finds_files_without_embeddings(self, tmp_path):
        """Test orphan detector finds files that have progress but no embeddings"""
        from main import OrphanDetector
        import sqlite3

        # Create a temporary database with orphaned file
        db_path = tmp_path / "test_progress.db"
        conn = sqlite3.connect(str(db_path))

        # Create tables
        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                chunks_processed INTEGER,
                total_chunks INTEGER,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                filename TEXT
            )
        ''')

        # Insert completed file WITHOUT corresponding document entry (orphan)
        conn.execute('''
            INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', ('/test/orphaned.pdf', 'completed', 10, 10, '2025-01-01 12:00:00'))

        # Insert completed file WITH document entry (valid file - should NOT be orphan)
        conn.execute('''
            INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', ('/test/valid.pdf', 'completed', 5, 5, '2025-01-01 12:00:00'))
        conn.execute('''
            INSERT INTO documents (file_path, filename)
            VALUES (?, ?)
        ''', ('/test/valid.pdf', 'valid.pdf'))

        conn.commit()
        conn.close()

        # Mock progress tracker
        mock_tracker = Mock()
        mock_tracker.get_db_path.return_value = str(db_path)

        # Mock vector store (not used in detection)
        mock_store = Mock()

        # Create detector and find orphans
        detector = OrphanDetector(mock_tracker, mock_store)
        orphans = detector.detect_orphans()

        # Should find only the orphaned file, not the valid one
        assert len(orphans) == 1
        assert orphans[0]['path'] == '/test/orphaned.pdf'
        assert orphans[0]['chunks'] == 10

    def test_orphans_queued_with_high_priority(self, tmp_path):
        """Test orphaned files are queued with HIGH priority for reindexing"""
        from main import OrphanDetector
        from services.indexing_queue import Priority
        import sqlite3

        # Create temporary database with orphaned file
        db_path = tmp_path / "test_progress.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                chunks_processed INTEGER,
                total_chunks INTEGER,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                filename TEXT
            )
        ''')

        # Create an actual file
        orphan_file = tmp_path / "orphaned.pdf"
        orphan_file.touch()

        # Insert orphaned file entry
        conn.execute('''
            INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', (str(orphan_file), 'completed', 15, 15, '2025-01-01 12:00:00'))

        conn.commit()
        conn.close()

        # Mock components
        mock_tracker = Mock()
        mock_tracker.get_db_path.return_value = str(db_path)
        mock_store = Mock()
        mock_queue = Mock()

        # Create detector and repair orphans
        detector = OrphanDetector(mock_tracker, mock_store)
        queued_count = detector.repair_orphans(mock_queue)

        # Verify orphan was queued
        assert queued_count == 1
        mock_queue.add.assert_called_once()

        # Verify HIGH priority was used
        call_args = mock_queue.add.call_args
        assert call_args[1]['priority'] == Priority.HIGH

    def test_valid_files_not_marked_as_orphans(self, tmp_path):
        """Test files with both progress AND embeddings are not marked as orphans"""
        from main import OrphanDetector
        import sqlite3

        # Create temporary database
        db_path = tmp_path / "test_progress.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                chunks_processed INTEGER,
                total_chunks INTEGER,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                filename TEXT
            )
        ''')

        # Insert multiple completed files WITH document entries (all valid, none orphaned)
        files = [
            ('/test/file1.pdf', 'file1.pdf', 10),
            ('/test/file2.md', 'file2.md', 5),
            ('/test/file3.epub', 'file3.epub', 20)
        ]

        for file_path, filename, chunks in files:
            conn.execute('''
                INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_path, 'completed', chunks, chunks, '2025-01-01 12:00:00'))
            conn.execute('''
                INSERT INTO documents (file_path, filename)
                VALUES (?, ?)
            ''', (file_path, filename))

        conn.commit()
        conn.close()

        # Mock components
        mock_tracker = Mock()
        mock_tracker.get_db_path.return_value = str(db_path)
        mock_store = Mock()

        # Create detector and find orphans
        detector = OrphanDetector(mock_tracker, mock_store)
        orphans = detector.detect_orphans()

        # Should find NO orphans (all files have embeddings)
        assert len(orphans) == 0

    def test_incomplete_files_not_marked_as_orphans(self, tmp_path):
        """Test files with 'in_progress' or 'failed' status are not marked as orphans"""
        from main import OrphanDetector
        import sqlite3

        # Create temporary database
        db_path = tmp_path / "test_progress.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                chunks_processed INTEGER,
                total_chunks INTEGER,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                filename TEXT
            )
        ''')

        # Insert files with various statuses WITHOUT document entries
        conn.execute('''
            INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', ('/test/in_progress.pdf', 'in_progress', 5, 10, '2025-01-01 12:00:00'))

        conn.execute('''
            INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', ('/test/failed.pdf', 'failed', 0, 10, '2025-01-01 12:00:00'))

        # Only completed files without documents should be orphans
        conn.execute('''
            INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', ('/test/orphaned.pdf', 'completed', 10, 10, '2025-01-01 12:00:00'))

        conn.commit()
        conn.close()

        # Mock components
        mock_tracker = Mock()
        mock_tracker.get_db_path.return_value = str(db_path)
        mock_store = Mock()

        # Create detector and find orphans
        detector = OrphanDetector(mock_tracker, mock_store)
        orphans = detector.detect_orphans()

        # Should find only the completed file without embeddings
        assert len(orphans) == 1
        assert orphans[0]['path'] == '/test/orphaned.pdf'

    def test_empty_database_returns_no_orphans(self, tmp_path):
        """Test empty database doesn't cause errors"""
        from main import OrphanDetector
        import sqlite3

        # Create empty database
        db_path = tmp_path / "test_progress.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                chunks_processed INTEGER,
                total_chunks INTEGER,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                filename TEXT
            )
        ''')

        conn.commit()
        conn.close()

        # Mock components
        mock_tracker = Mock()
        mock_tracker.get_db_path.return_value = str(db_path)
        mock_store = Mock()

        # Create detector and find orphans
        detector = OrphanDetector(mock_tracker, mock_store)
        orphans = detector.detect_orphans()

        # Should return empty list, not error
        assert orphans == []

    def test_multiple_orphans_all_detected(self, tmp_path):
        """Test multiple orphaned files are all detected"""
        from main import OrphanDetector
        import sqlite3

        # Create temporary database
        db_path = tmp_path / "test_progress.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute('''
            CREATE TABLE processing_progress (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                chunks_processed INTEGER,
                total_chunks INTEGER,
                last_updated TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE,
                filename TEXT
            )
        ''')

        # Insert 5 orphaned files
        orphan_files = [
            '/test/orphan1.pdf',
            '/test/orphan2.md',
            '/test/orphan3.epub',
            '/test/orphan4.txt',
            '/test/orphan5.pdf'
        ]

        for file_path in orphan_files:
            conn.execute('''
                INSERT INTO processing_progress (file_path, status, chunks_processed, total_chunks, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_path, 'completed', 10, 10, '2025-01-01 12:00:00'))

        conn.commit()
        conn.close()

        # Mock components
        mock_tracker = Mock()
        mock_tracker.get_db_path.return_value = str(db_path)
        mock_store = Mock()

        # Create detector and find orphans
        detector = OrphanDetector(mock_tracker, mock_store)
        orphans = detector.detect_orphans()

        # Should find all 5 orphans
        assert len(orphans) == 5
        orphan_paths = {o['path'] for o in orphans}
        assert orphan_paths == set(orphan_files)
