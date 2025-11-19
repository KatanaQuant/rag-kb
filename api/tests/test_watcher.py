"""
Tests for file watcher functionality
"""
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from watcher import (
    DebounceTimer,
    FileChangeCollector,
    DocumentEventHandler,
    IndexingCoordinator,
    FileWatcherService
)


class TestDebounceTimer:
    """Test debounce timer"""

    def test_timer_triggers_after_delay(self):
        """Test callback triggered after delay"""
        callback = Mock()
        timer = DebounceTimer(delay=0.1, callback=callback)

        timer.trigger()
        time.sleep(0.05)
        callback.assert_not_called()

        time.sleep(0.1)
        callback.assert_called_once()

    def test_timer_resets_on_trigger(self):
        """Test timer resets when triggered again"""
        callback = Mock()
        timer = DebounceTimer(delay=0.1, callback=callback)

        timer.trigger()
        time.sleep(0.05)
        timer.trigger()  # Reset
        time.sleep(0.08)
        callback.assert_not_called()

        time.sleep(0.05)
        callback.assert_called_once()

    def test_cancel_prevents_execution(self):
        """Test cancel stops callback"""
        callback = Mock()
        timer = DebounceTimer(delay=0.1, callback=callback)

        timer.trigger()
        timer.cancel()
        time.sleep(0.15)
        callback.assert_not_called()


class TestFileChangeCollector:
    """Test file change collector"""

    def test_add_file(self):
        """Test adding files"""
        collector = FileChangeCollector()
        file1 = Path("/test/file1.pdf")
        file2 = Path("/test/file2.md")

        collector.add(file1)
        collector.add(file2)

        assert collector.count() == 2

    def test_deduplicate_files(self):
        """Test duplicate files are ignored"""
        collector = FileChangeCollector()
        file1 = Path("/test/file1.pdf")

        collector.add(file1)
        collector.add(file1)
        collector.add(file1)

        assert collector.count() == 1

    def test_get_and_clear(self):
        """Test getting and clearing collection"""
        collector = FileChangeCollector()
        file1 = Path("/test/file1.pdf")
        file2 = Path("/test/file2.md")

        collector.add(file1)
        collector.add(file2)

        files = collector.get_and_clear()
        assert len(files) == 2
        assert file1 in files
        assert file2 in files
        assert collector.count() == 0


class TestDocumentEventHandler:
    """Test event handler"""

    def test_supported_extensions(self):
        """Test supported file types"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        event = Mock()
        event.is_directory = False
        event.src_path = "/test/file.pdf"
        handler.on_created(event)

        assert collector.count() == 1

    def test_unsupported_extensions_ignored(self):
        """Test unsupported files are ignored"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        event = Mock()
        event.is_directory = False
        event.src_path = "/test/file.jpg"
        handler.on_created(event)

        assert collector.count() == 0

    def test_directories_ignored(self):
        """Test directories are ignored"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        event = Mock()
        event.is_directory = True
        event.src_path = "/test/folder"
        handler.on_created(event)

        assert collector.count() == 0

    def test_timer_triggered_on_change(self):
        """Test timer is triggered when file changes"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        event = Mock()
        event.is_directory = False
        event.src_path = "/test/file.pdf"
        handler.on_created(event)

        timer.trigger.assert_called_once()


class TestIndexingCoordinator:
    """Test indexing coordinator"""

    def test_process_empty_collection(self):
        """Test processing with no changes"""
        indexer = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        coordinator.process_changes()
        # Should not crash

    def test_process_files(self):
        """Test processing files"""
        indexer = Mock()
        indexer.index_file = Mock(return_value=(10, False))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        file2 = Path("/test/file2.md")
        collector.add(file1)
        collector.add(file2)

        coordinator.process_changes()

        assert indexer.index_file.call_count == 2
        assert collector.count() == 0

    def test_batch_size_limit(self):
        """Test batch size is respected"""
        indexer = Mock()
        indexer.index_file = Mock(return_value=(10, False))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=2)

        for i in range(5):
            collector.add(Path(f"/test/file{i}.pdf"))

        coordinator.process_changes()

        assert indexer.index_file.call_count == 2

    def test_shows_processing_before_result(self, capsys):
        """Test: Shows 'Processing...' message BEFORE showing success/failure"""
        indexer = Mock()
        indexer.index_file = Mock(return_value=(10, False))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/document.pdf")
        collector.add(file1)

        coordinator.process_changes()

        captured = capsys.readouterr()
        output_lines = captured.out.strip().split('\n')

        # Should have at least 3 lines: "Processing...", "  Processing document.pdf...", "  ✓ document.pdf: X chunks"
        assert len(output_lines) >= 3
        assert "Processing 1 changed file" in output_lines[0]
        assert "Processing document.pdf" in output_lines[1]
        assert "✓ document.pdf" in output_lines[2]

    def test_shows_processing_before_error(self, capsys):
        """Test: Shows 'Processing...' message BEFORE showing error"""
        indexer = Mock()
        indexer.index_file = Mock(side_effect=Exception("Test error"))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/broken.epub")
        collector.add(file1)

        coordinator.process_changes()

        captured = capsys.readouterr()
        output_lines = captured.out.strip().split('\n')

        # Should show processing before error
        assert len(output_lines) >= 3
        assert "Processing 1 changed file" in output_lines[0]
        assert "Processing broken.epub" in output_lines[1]
        assert "✗ broken.epub" in output_lines[2]

    def test_error_handling(self):
        """Test errors don't stop processing"""
        indexer = Mock()
        indexer.index_file = Mock(side_effect=[Exception("Error"), (10, False)])
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        file2 = Path("/test/file2.pdf")
        collector.add(file1)
        collector.add(file2)

        coordinator.process_changes()

        assert indexer.index_file.call_count == 2


class TestFileWatcherService:
    """Test file watcher service"""

    def test_initialization(self):
        """Test service initialization"""
        indexer = Mock()
        watch_path = Path("/test")
        service = FileWatcherService(
            watch_path=watch_path,
            indexer=indexer,
            debounce_seconds=1.0,
            batch_size=50
        )

        assert service.watch_path == watch_path
        assert service.collector is not None
        assert service.coordinator is not None
        assert service.timer is not None
        assert service.handler is not None

    def test_debounce_callback_processes_changes(self):
        """Test debounce triggers indexing"""
        indexer = Mock()
        indexer.index_file = Mock(return_value=(10, False))
        watch_path = Path("/test")
        service = FileWatcherService(
            watch_path=watch_path,
            indexer=indexer,
            debounce_seconds=0.1,
            batch_size=50
        )

        file1 = Path("/test/file1.pdf")
        service.collector.add(file1)
        service._on_debounce()

        indexer.index_file.assert_called_once()

    def test_error_during_indexing_handled(self):
        """Test errors during indexing are caught"""
        indexer = Mock()
        indexer.index_file = Mock(side_effect=Exception("Test error"))
        watch_path = Path("/test")
        service = FileWatcherService(
            watch_path=watch_path,
            indexer=indexer,
            debounce_seconds=0.1,
            batch_size=50
        )

        file1 = Path("/test/file1.pdf")
        service.collector.add(file1)
        service._on_debounce()  # Should not raise


class TestIndexingCoordinatorWithTupleReturn:
    """Test coordinator handles tuple return from index_file correctly"""

    def test_index_file_returns_tuple_success(self, capsys):
        """Test coordinator handles (chunks, was_skipped) tuple correctly"""
        indexer = Mock()
        # Real index_file returns (chunks, was_skipped)
        indexer.index_file = Mock(return_value=(10, False))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        collector.add(file1)

        # Should properly unpack tuple and show success message
        coordinator.process_changes()
        captured = capsys.readouterr()

        # Should show success, not failure
        assert "✓" in captured.out
        assert "10 chunks" in captured.out
        assert "✗" not in captured.out
        assert indexer.index_file.call_count == 1

    def test_index_file_returns_tuple_skipped(self, capsys):
        """Test coordinator handles skipped file (0 chunks, was_skipped=True)"""
        indexer = Mock()
        # File was skipped (already indexed)
        indexer.index_file = Mock(return_value=(0, True))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        collector.add(file1)

        coordinator.process_changes()
        captured = capsys.readouterr()

        # Skipped files should not show as errors
        assert "✗" not in captured.out
        assert indexer.index_file.call_count == 1

    def test_index_file_returns_tuple_no_chunks(self, capsys):
        """Test coordinator handles file with no chunks (0 chunks, was_skipped=False)"""
        indexer = Mock()
        # File was processed but had no chunks (e.g., empty file)
        indexer.index_file = Mock(return_value=(0, False))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(indexer, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        collector.add(file1)

        coordinator.process_changes()
        captured = capsys.readouterr()

        # Files with 0 chunks should not show as errors
        assert "✗" not in captured.out
        assert indexer.index_file.call_count == 1
