"""Tests for pre-stage skip check in pipeline coordinator.

Issue 2.2: All files were going into chunk_queue before skip-check.
Fix: Check is_document_indexed() in add_file() BEFORE queuing.

This keeps chunk_queue small - only files needing processing are queued.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from queue import Queue

from pipeline.pipeline_coordinator import PipelineCoordinator
from pipeline.indexing_queue import QueueItem


class TestPreStageSkipCheck:
    """Test that already-indexed files are filtered before chunk_queue"""

    @pytest.fixture
    def mock_coordinator(self):
        """Create coordinator with mocked dependencies"""
        with patch('pipeline.pipeline_coordinator.PipelineQueues') as mock_queues, \
             patch('pipeline.pipeline_coordinator.EmbedWorkerPool'), \
             patch('pipeline.pipeline_coordinator.StageWorker'), \
             patch('pipeline.pipeline_coordinator.ProgressLogger'), \
             patch('pipeline.pipeline_coordinator.SkipBatcher') as mock_batcher:
            
            # Create mock queues
            mock_queues_instance = MagicMock()
            mock_queues_instance.chunk_queue = Queue()
            mock_queues.return_value = mock_queues_instance
            
            # Create mock embedding service with store
            mock_embedding_service = MagicMock()
            mock_store = MagicMock()
            mock_embedding_service.store = mock_store
            
            coordinator = PipelineCoordinator(
                processor=MagicMock(),
                indexer=MagicMock(),
                embedding_service=mock_embedding_service
            )
            
            return coordinator, mock_store

    def test_already_indexed_file_not_queued(self, mock_coordinator):
        """Test: Already indexed files are filtered out before queue"""
        coordinator, mock_store = mock_coordinator
        
        # Mock: file is already indexed
        mock_store.is_document_indexed.return_value = True
        
        # Create queue item
        with patch('pipeline.pipeline_coordinator.DocumentFile') as mock_doc_file:
            mock_doc_file.from_path.return_value = MagicMock(hash='abc123')
            
            item = QueueItem(priority=0, path=Path('/test/file.pdf'), force=False)
            coordinator.add_file(item)
        
        # Should NOT be in chunk_queue
        assert coordinator.queues.chunk_queue.qsize() == 0

    def test_new_file_is_queued(self, mock_coordinator):
        """Test: New files (not indexed) are added to queue"""
        coordinator, mock_store = mock_coordinator
        
        # Mock: file is NOT indexed
        mock_store.is_document_indexed.return_value = False
        
        with patch('pipeline.pipeline_coordinator.DocumentFile') as mock_doc_file:
            mock_doc_file.from_path.return_value = MagicMock(hash='abc123')
            
            item = QueueItem(priority=0, path=Path('/test/file.pdf'), force=False)
            coordinator.add_file(item)
        
        # Should be in chunk_queue
        assert coordinator.queues.chunk_queue.qsize() == 1

    def test_force_bypasses_skip_check(self, mock_coordinator):
        """Test: force=True bypasses the skip check"""
        coordinator, mock_store = mock_coordinator
        
        # Mock: file is already indexed
        mock_store.is_document_indexed.return_value = True
        
        with patch('pipeline.pipeline_coordinator.DocumentFile') as mock_doc_file:
            mock_doc_file.from_path.return_value = MagicMock(hash='abc123')
            
            # force=True should bypass skip
            item = QueueItem(priority=0, path=Path('/test/file.pdf'), force=True)
            coordinator.add_file(item)
        
        # Should be in chunk_queue despite being indexed
        assert coordinator.queues.chunk_queue.qsize() == 1

    def test_skip_records_to_batcher(self, mock_coordinator):
        """Test: Skipped files are recorded to skip batcher"""
        coordinator, mock_store = mock_coordinator
        
        # Mock: file is already indexed
        mock_store.is_document_indexed.return_value = True
        
        with patch('pipeline.pipeline_coordinator.DocumentFile') as mock_doc_file:
            mock_doc_file.from_path.return_value = MagicMock(hash='abc123')
            
            item = QueueItem(priority=0, path=Path('/test/file.pdf'), force=False)
            coordinator.add_file(item)
        
        # Should record skip
        coordinator.skip_batcher.record_skip.assert_called_once_with('file.pdf', 'already indexed')

    def test_error_during_check_lets_file_through(self, mock_coordinator):
        """Test: If skip check fails, file is queued for proper error handling"""
        coordinator, mock_store = mock_coordinator
        
        with patch('pipeline.pipeline_coordinator.DocumentFile') as mock_doc_file:
            # Simulate error during check
            mock_doc_file.from_path.side_effect = Exception("File read error")
            
            item = QueueItem(priority=0, path=Path('/test/file.pdf'), force=False)
            coordinator.add_file(item)
        
        # File should be queued - let chunk_stage handle the error properly
        assert coordinator.queues.chunk_queue.qsize() == 1
