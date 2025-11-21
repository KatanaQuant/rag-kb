"""Tests for pipeline coordinator logging - TDD for correct stage labels

Issue: Files that are already indexed should not log with [Chunk] prefix,
since they are skipped before the chunking stage actually happens.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from services.pipeline_coordinator import PipelineCoordinator
from services.indexing_queue import QueueItem, Priority


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

    @patch('services.pipeline_coordinator.DocumentFile')
    def test_already_indexed_file_logs_skip_not_chunk(self, mock_doc_class, mock_services, mock_doc_file, capsys):
        """Files already indexed should log [Skip] not [Chunk]"""
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

        # Process the file
        result = coordinator._chunk_stage(item)

        # Verify: Should return None (skipped)
        assert result is None

        # Verify: Should log [Skip] not [Chunk]
        captured = capsys.readouterr()
        assert "[Skip]" in captured.out
        assert "already indexed" in captured.out
        # Should NOT have separate [Chunk] line before the skip message
        lines = [line for line in captured.out.split('\n') if line.strip()]
        chunk_lines = [line for line in lines if '[Chunk]' in line and 'already indexed' not in line]
        assert len(chunk_lines) == 0, f"Found unexpected [Chunk] log lines: {chunk_lines}"

    @patch('services.pipeline_coordinator.DocumentFile')
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
        assert "2 chunks created" in captured.out

    @patch('services.pipeline_coordinator.DocumentFile')
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
