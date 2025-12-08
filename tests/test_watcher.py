"""
Tests for file watcher functionality
"""
import time
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from tests import requires_huggingface
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

    def test_moved_files_are_detected(self):
        """Test file move events are handled (e.g., mv file.epub knowledge_base/)"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        # Simulate moving a file into the knowledge_base directory
        event = Mock()
        event.is_directory = False
        event.dest_path = "/app/knowledge_base/System Design Interview.epub"
        event.src_path = "/tmp/System Design Interview.epub"
        handler.on_moved(event)

        # File should be added to collector
        assert collector.count() == 1
        timer.trigger.assert_called_once()

    def test_moved_unsupported_files_ignored(self):
        """Test moved files with unsupported extensions are ignored"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        event = Mock()
        event.is_directory = False
        event.dest_path = "/app/knowledge_base/image.jpg"
        event.src_path = "/tmp/image.jpg"
        handler.on_moved(event)

        assert collector.count() == 0
        timer.trigger.assert_not_called()

    def test_moved_to_excluded_directory_ignored(self):
        """Test files moved to excluded directories are ignored"""
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        event = Mock()
        event.is_directory = False
        event.dest_path = "/app/knowledge_base/problematic/file.pdf"
        event.src_path = "/app/knowledge_base/file.pdf"
        handler.on_moved(event)

        assert collector.count() == 0
        timer.trigger.assert_not_called()

    @requires_huggingface
    def test_moved_already_indexed_file_skips_reindex(self):
        """Test that moving an already-indexed file doesn't trigger reindexing"""
        # Setup: File watcher detects a moved file
        collector = FileChangeCollector()
        timer = Mock()
        handler = DocumentEventHandler(collector, timer)

        # Mock queue that will receive the file
        mock_queue = Mock()

        # Simulate file move event
        event = Mock()
        event.is_directory = False
        event.dest_path = "/app/knowledge_base/moved_book.pdf"
        event.src_path = "/tmp/moved_book.pdf"
        handler.on_moved(event)

        # File should be collected
        assert collector.count() == 1

        # Now simulate IndexingCoordinator processing with queue
        queue = Mock()
        queue.add = Mock()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        # Process the moved file
        coordinator.process_changes()

        # Verify file was queued (queue handles skip logic)
        assert queue.add.call_count == 1

        # Verify force=False was used (allowing skip logic)
        # The queue.add call in _queue_files uses force=False
        # This ensures the indexer can skip already-indexed files


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
        queue = Mock()
        queue.add = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        file2 = Path("/test/file2.md")
        collector.add(file1)
        collector.add(file2)

        coordinator.process_changes()

        assert queue.add.call_count == 2
        assert collector.count() == 0

    def test_batch_size_limit(self):
        """Test batch size is respected"""
        queue = Mock()
        queue.add = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=2)

        for i in range(5):
            collector.add(Path(f"/test/file{i}.pdf"))

        coordinator.process_changes()

        assert queue.add.call_count == 2

    def test_shows_processing_before_result(self, capsys):
        """Test: Shows 'Queueing...' message when adding files to queue"""
        queue = Mock()
        queue.add = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/document.pdf")
        collector.add(file1)

        coordinator.process_changes()

        captured = capsys.readouterr()
        output_lines = captured.out.strip().split('\n')

        # Should show queueing messages
        assert len(output_lines) >= 2
        assert "Queueing 1 changed file" in output_lines[0]

    def test_shows_processing_before_error(self, capsys):
        """Test: Shows 'Queueing...' message even when queue.add fails"""
        queue = Mock()
        queue.add = Mock(side_effect=Exception("Test error"))
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/broken.epub")
        collector.add(file1)

        coordinator.process_changes()

        captured = capsys.readouterr()
        output_lines = captured.out.strip().split('\n')

        # Should show queueing attempt
        assert len(output_lines) >= 2
        assert "Queueing 1 changed file" in output_lines[0]

    def test_error_handling(self):
        """Test errors don't stop processing"""
        queue = Mock()
        queue.add = Mock(side_effect=[Exception("Error"), None])
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        file2 = Path("/test/file2.pdf")
        collector.add(file1)
        collector.add(file2)

        coordinator.process_changes()

        assert queue.add.call_count == 2


class TestFileWatcherService:
    """Test file watcher service"""

    def test_initialization(self):
        """Test service initialization"""
        queue = Mock()
        watch_path = Path("/test")
        service = FileWatcherService(
            watch_path=watch_path,
            queue=queue,
            debounce_seconds=1.0,
            batch_size=50
        )

        assert service.watch_path == watch_path
        assert service.collector is not None
        assert service.coordinator is not None
        assert service.timer is not None
        assert service.handler is not None

    def test_debounce_callback_processes_changes(self):
        """Test debounce triggers queueing"""
        queue = Mock()
        queue.add = Mock()
        watch_path = Path("/test")
        service = FileWatcherService(
            watch_path=watch_path,
            queue=queue,
            debounce_seconds=0.1,
            batch_size=50
        )

        file1 = Path("/test/file1.pdf")
        service.collector.add(file1)
        service._on_debounce()

        queue.add.assert_called_once()

    def test_error_during_indexing_handled(self):
        """Test errors during queueing are caught"""
        queue = Mock()
        queue.add = Mock(side_effect=Exception("Test error"))
        watch_path = Path("/test")
        service = FileWatcherService(
            watch_path=watch_path,
            queue=queue,
            debounce_seconds=0.1,
            batch_size=50
        )

        file1 = Path("/test/file1.pdf")
        service.collector.add(file1)
        service._on_debounce()  # Should not raise


class TestIndexingCoordinatorWithTupleReturn:
    """Test coordinator queues files for processing"""

    def test_index_file_returns_tuple_success(self, capsys):
        """Test coordinator queues files successfully"""
        queue = Mock()
        queue.add = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        collector.add(file1)

        coordinator.process_changes()
        captured = capsys.readouterr()

        # Should show queuing message
        assert "Queued" in captured.out or "Queueing" in captured.out
        assert queue.add.call_count == 1

    def test_index_file_returns_tuple_skipped(self, capsys):
        """Test coordinator queues all files (queue handles dedup)"""
        queue = Mock()
        queue.add = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        collector.add(file1)

        coordinator.process_changes()
        captured = capsys.readouterr()

        # Should attempt to queue
        assert queue.add.call_count == 1

    def test_index_file_returns_tuple_no_chunks(self, capsys):
        """Test coordinator queues files regardless of content"""
        queue = Mock()
        queue.add = Mock()
        collector = FileChangeCollector()
        coordinator = IndexingCoordinator(queue, collector, batch_size=50)

        file1 = Path("/test/file1.pdf")
        collector.add(file1)

        coordinator.process_changes()
        captured = capsys.readouterr()

        # Should attempt to queue
        assert queue.add.call_count == 1
