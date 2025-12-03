"""Tests for pipeline coordinator logging - TDD for correct stage labels

Issue: Files that are already indexed should not log with [Chunk] prefix,
since they are skipped before the chunking stage actually happens.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from pipeline.pipeline_coordinator import PipelineCoordinator
from pipeline.indexing_queue import QueueItem, Priority


class TestPipelineLogging:
    """Test correct logging labels for pipeline stages"""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing"""
        processor = Mock()
        indexer = Mock()
        embedding_service = Mock()
        embedding_service.store = Mock()
        return processor, indexer, embedding_service

    @pytest.fixture
    def mock_doc_file(self):
        """Mock DocumentFile to avoid file system access"""
        mock_file = Mock()
        mock_file.path = Path("/test/file.pdf")
        mock_file.hash = "mock_hash_123"
        return mock_file

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_already_indexed_file_records_skip(self, mock_doc_class, mock_services, mock_doc_file):
        """Files already indexed should be recorded as skipped via skip_batcher"""
        processor, indexer, embedding_service = mock_services

        # Mock DocumentFile.from_path to return our mock
        mock_doc_class.from_path.return_value = mock_doc_file

        # Setup: File is already indexed
        embedding_service.store.is_document_indexed.return_value = True

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        # Create a queue item for an already-indexed file
        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/already_indexed.pdf"),
            force=False
        )

        # Mock the skip_batcher to verify it's called
        coordinator.skip_batcher = Mock()

        # Process the file
        result = coordinator._chunk_stage(item)

        # Verify: Should return None (skipped)
        assert result is None

        # Verify: skip_batcher.record_skip was called with correct args
        coordinator.skip_batcher.record_skip.assert_called_once_with(
            "already_indexed.pdf", "already indexed"
        )

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_new_file_logs_chunk_correctly(self, mock_doc_class, mock_services, mock_doc_file, capsys):
        """New files being chunked should log [Chunk]"""
        processor, indexer, embedding_service = mock_services

        # Mock DocumentFile.from_path to return our mock
        mock_doc_class.from_path.return_value = mock_doc_file

        # Setup: File is NOT indexed yet
        embedding_service.store.is_document_indexed.return_value = False

        # Mock processor to return chunks
        mock_chunks = [
            {'content': 'chunk1', 'metadata': {}},
            {'content': 'chunk2', 'metadata': {}}
        ]
        processor.process_file.return_value = mock_chunks

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/new_file.pdf"),
            force=False
        )

        # Process the file
        result = coordinator._chunk_stage(item)

        # Verify: Should return ChunkedDocument
        assert result is not None
        assert len(result.chunks) == 2

        # Verify: Should log [Chunk] with chunk count
        captured = capsys.readouterr()
        assert "[Chunk]" in captured.out
        assert "2 chunks complete" in captured.out

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_forced_file_always_chunks(self, mock_doc_class, mock_services, mock_doc_file, capsys):
        """Files with force=True should always chunk, even if indexed"""
        processor, indexer, embedding_service = mock_services

        # Mock DocumentFile.from_path to return our mock
        mock_doc_class.from_path.return_value = mock_doc_file

        # Setup: File is indexed, but force=True overrides
        embedding_service.store.is_document_indexed.return_value = True

        mock_chunks = [{'content': 'forced chunk', 'metadata': {}}]
        processor.process_file.return_value = mock_chunks

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.HIGH,
            path=Path("/test/forced.pdf"),
            force=True  # Force reprocessing
        )

        # Process the file
        result = coordinator._chunk_stage(item)

        # Verify: Should NOT skip, should return chunks
        assert result is not None

        # Verify: Should log [Chunk] not [Skip]
        captured = capsys.readouterr()
        assert "[Chunk]" in captured.out
        assert "already indexed" not in captured.out

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_epub_conversion_logs_success_not_zero_chunks(self, mock_doc_class, mock_services, capsys):
        """EPUB conversion should log success message, not '0 chunks extracted'

        Issue: EPUB files are converted to PDF, then the EPUB is moved to original/.
        The EPUB extraction intentionally returns 0 chunks because the PDF will be
        processed separately. The log should say 'conversion complete' not 'no chunks'.

        Note: EPUBs are routed to _handle_epub_conversion() via add_file(),
        NOT through _chunk_stage(). This test verifies the correct code path.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for EPUB file
        epub_file = Mock()
        epub_file.path = Path("/test/book.epub")
        epub_file.hash = "epub_hash_123"
        mock_doc_class.from_path.return_value = epub_file

        # Setup: File is NOT indexed
        embedding_service.store.is_document_indexed.return_value = False

        # EPUB conversion returns empty chunks (PDF will be processed separately)
        processor.process_file.return_value = []

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/book.epub"),
            force=False
        )

        # Process the EPUB via add_file (which routes to _handle_epub_conversion)
        coordinator.add_file(item)

        # Verify: Should log [Convert] with conversion success, NOT "no chunks extracted"
        captured = capsys.readouterr()
        assert "[Convert]" in captured.out
        assert "conversion complete" in captured.out.lower()
        # The misleading message should NOT appear
        assert "no chunks extracted" not in captured.out

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_heartbeat_stops_on_rejection(self, mock_doc_class, mock_services, capsys):
        """Heartbeat should stop when file is rejected by security

        Bug: When a file is rejected, _chunk_stage() returns early without
        calling log_complete(), leaving the heartbeat thread running forever.
        This causes confusing "processing... 540s elapsed" messages after rejection.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for rejected file
        rejected_file = Mock()
        rejected_file.path = Path("/test/rejected.md")
        rejected_file.hash = "rejected_hash"
        mock_doc_class.from_path.return_value = rejected_file

        # Setup: File is NOT indexed (so it goes through processing)
        embedding_service.store.is_document_indexed.return_value = False

        # File is rejected - returns empty chunks
        processor.process_file.return_value = []
        # Mark as rejected
        processor.is_rejected.return_value = True

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/rejected.md"),
            force=False
        )

        # Process the file (will be rejected)
        result = coordinator._chunk_stage(item)

        # Verify: Should return None (rejected)
        assert result is None

        # Verify: Heartbeat should be stopped (key should not exist)
        heartbeat_key = "Chunk:rejected.md"
        assert heartbeat_key not in coordinator.progress_logger.heartbeat_threads
        assert heartbeat_key not in coordinator.progress_logger.heartbeat_stop_flags

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_heartbeat_stops_on_empty_extraction(self, mock_doc_class, mock_services, capsys):
        """Heartbeat should stop when file produces no chunks (not rejected)

        Some files may extract successfully but produce 0 chunks (e.g., empty files).
        The heartbeat should still be stopped and a proper message logged.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for empty file
        empty_file = Mock()
        empty_file.path = Path("/test/empty.go")
        empty_file.hash = "empty_hash"
        mock_doc_class.from_path.return_value = empty_file

        # Setup: File is NOT indexed
        embedding_service.store.is_document_indexed.return_value = False

        # File extracts but produces no chunks
        processor.process_file.return_value = []
        # NOT rejected - just empty
        processor.is_rejected.return_value = False

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/empty.go"),
            force=False
        )

        # Process the file
        result = coordinator._chunk_stage(item)

        # Verify: Should return None
        assert result is None

        # Verify: Heartbeat should be stopped
        heartbeat_key = "Chunk:empty.go"
        assert heartbeat_key not in coordinator.progress_logger.heartbeat_threads
        assert heartbeat_key not in coordinator.progress_logger.heartbeat_stop_flags

        # Verify: Should log "no chunks extracted" message
        captured = capsys.readouterr()
        assert "no chunks extracted" in captured.out


class TestPreQueueValidation:
    """Test pre-queue validation for clean rejection logs

    Issue: Rejected files should NOT get [Chunk] prefix because they never
    actually enter the chunking stage. Validation should happen BEFORE
    adding to queue, resulting in clean logs:

    BEFORE (misleading):
        [Chunk] malware.exe
        REJECTED (security): malware.exe - Malware detected
        [Chunk] malware.exe - 0 chunks complete

    AFTER (clean):
        REJECTED (security): malware.exe - Malware detected
    """

    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing"""
        processor = Mock()
        indexer = Mock()
        embedding_service = Mock()
        embedding_service.store = Mock()
        return processor, indexer, embedding_service

    @pytest.fixture
    def mock_validation_result(self):
        """Create mock validation result"""
        result = Mock()
        result.is_valid = False
        result.reason = "File is empty"
        result.validation_check = "empty_file"
        return result

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_rejected_file_no_chunk_prefix(self, mock_doc_class, mock_services, mock_validation_result, capsys):
        """Rejected files should NOT log [Chunk] prefix

        When a file fails security validation, it should be rejected
        BEFORE entering the chunk stage, so no [Chunk] appears in logs.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for file that will be rejected
        rejected_file = Mock()
        rejected_file.path = Path("/test/empty_file.py")
        rejected_file.name = "empty_file.py"
        rejected_file.hash = "test_hash"
        mock_doc_class.from_path.return_value = rejected_file

        # Setup: Validator returns failure
        processor.validator = Mock()
        processor.validator.validate.return_value = mock_validation_result

        # Setup: Quarantine manager mock
        processor.quarantine = Mock()

        # Setup: Tracker mock
        processor.tracker = Mock()

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/empty_file.py"),
            force=False
        )

        # Add file (should validate and reject BEFORE queue)
        coordinator.add_file(item)

        # Verify: Should NOT log [Chunk] prefix
        captured = capsys.readouterr()
        assert "[Chunk]" not in captured.out

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_rejected_file_logs_rejection_message(self, mock_doc_class, mock_services, mock_validation_result, capsys):
        """Rejected files should log REJECTED message only

        The rejection message should be the ONLY output for a rejected file,
        with no misleading stage prefixes.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for file that will be rejected
        rejected_file = Mock()
        rejected_file.path = Path("/test/malware.exe")
        rejected_file.name = "malware.exe"
        rejected_file.hash = "test_hash"
        mock_doc_class.from_path.return_value = rejected_file

        # Setup: Validator returns failure with malware reason
        mock_validation_result.reason = "Malware detected: EICAR-Test-File"
        mock_validation_result.validation_check = "malware"
        processor.validator = Mock()
        processor.validator.validate.return_value = mock_validation_result

        # Setup: Quarantine manager mock
        processor.quarantine = Mock()

        # Setup: Tracker mock
        processor.tracker = Mock()

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/malware.exe"),
            force=False
        )

        # Add file
        coordinator.add_file(item)

        # Verify: Should log REJECTED message
        captured = capsys.readouterr()
        assert "REJECTED" in captured.out
        assert "malware.exe" in captured.out

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_valid_file_enters_queue(self, mock_doc_class, mock_services, capsys):
        """Valid files should pass validation and enter the queue

        Files that pass security validation should be added to chunk_queue
        normally and will get [Chunk] prefix when actually processed.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for valid file
        valid_file = Mock()
        valid_file.path = Path("/test/valid.py")
        valid_file.name = "valid.py"
        valid_file.hash = "test_hash"
        mock_doc_class.from_path.return_value = valid_file

        # Setup: Validator returns success
        valid_result = Mock()
        valid_result.is_valid = True
        processor.validator = Mock()
        processor.validator.validate.return_value = valid_result

        # Setup: File is NOT already indexed (so it passes skip check)
        embedding_service.store.is_document_indexed.return_value = False

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/valid.py"),
            force=False
        )

        # Mock queue to verify file is added
        coordinator.queues.chunk_queue = Mock()

        # Add file
        coordinator.add_file(item)

        # Verify: Should be added to chunk_queue
        coordinator.queues.chunk_queue.put.assert_called_once_with(item)

        # Verify: No REJECTED message
        captured = capsys.readouterr()
        assert "REJECTED" not in captured.out

    @patch('pipeline.pipeline_coordinator.DocumentFile')
    def test_rejected_file_not_queued(self, mock_doc_class, mock_services, mock_validation_result):
        """Rejected files should NOT be added to the queue

        Files that fail validation should be rejected immediately,
        never entering the chunk queue.
        """
        processor, indexer, embedding_service = mock_services

        # Create mock for rejected file
        rejected_file = Mock()
        rejected_file.path = Path("/test/bad.py")
        rejected_file.name = "bad.py"
        rejected_file.hash = "test_hash"
        mock_doc_class.from_path.return_value = rejected_file

        # Setup: Validator returns failure
        processor.validator = Mock()
        processor.validator.validate.return_value = mock_validation_result
        processor.quarantine = Mock()
        processor.tracker = Mock()

        coordinator = PipelineCoordinator(processor, indexer, embedding_service)

        item = QueueItem(
            priority=Priority.NORMAL,
            path=Path("/test/bad.py"),
            force=False
        )

        # Mock queue to verify file is NOT added
        coordinator.queues.chunk_queue = Mock()

        # Add file
        coordinator.add_file(item)

        # Verify: Should NOT be added to chunk_queue
        coordinator.queues.chunk_queue.put.assert_not_called()
