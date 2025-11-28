"""Tests for queue deduplication to prevent duplicate processing.

Issue: resume_incomplete_processing() was re-queuing files that were
already in the queue, causing duplicate processing.

Fix: IndexingQueue.add() now ALWAYS checks if file is already queued,
regardless of force flag. force=True only affects reindexing behavior,
not queue deduplication.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.indexing_queue import IndexingQueue, Priority


class TestQueueDeduplication:
    """Test that queue prevents duplicate entries"""

    @pytest.fixture
    def queue(self):
        return IndexingQueue()

    def test_duplicate_file_not_queued_twice(self, queue):
        """Test: Same file queued twice should only appear once"""
        path = Path("/test/file.pdf")
        
        queue.add(path, priority=Priority.NORMAL)
        queue.add(path, priority=Priority.NORMAL)
        
        assert queue.size() == 1

    def test_duplicate_file_with_force_still_not_queued_twice(self, queue):
        """Test: force=True should NOT bypass queue deduplication
        
        This is the bug fix - force is for reindexing, not for
        bypassing the queue deduplication check.
        """
        path = Path("/test/file.pdf")
        
        queue.add(path, priority=Priority.NORMAL)
        queue.add(path, priority=Priority.HIGH, force=True)  # Bug was here
        
        assert queue.size() == 1, "force=True should not bypass queue deduplication"

    def test_force_flag_still_passed_to_item(self, queue):
        """Test: force flag is still passed through for reindexing"""
        path = Path("/test/file.pdf")
        
        queue.add(path, priority=Priority.HIGH, force=True)
        
        item = queue.get(timeout=1.0)
        assert item is not None
        assert item.force == True

    def test_different_files_both_queued(self, queue):
        """Test: Different files are both queued"""
        path1 = Path("/test/file1.pdf")
        path2 = Path("/test/file2.pdf")
        
        queue.add(path1, priority=Priority.NORMAL)
        queue.add(path2, priority=Priority.NORMAL)
        
        assert queue.size() == 2

    def test_file_can_be_requeued_after_mark_complete(self, queue):
        """Test: File can be queued again after mark_complete()

        Files stay tracked after dequeue to prevent race conditions.
        Only mark_complete() removes from tracking set.
        """
        path = Path("/test/file.pdf")

        queue.add(path, priority=Priority.NORMAL)
        item = queue.get(timeout=1.0)
        assert item is not None

        # After dequeue, file is STILL tracked - cannot re-add
        queue.add(path, priority=Priority.NORMAL)
        assert queue.size() == 0  # Not added - still tracked

        # After mark_complete, file can be re-queued
        queue.mark_complete(path)
        queue.add(path, priority=Priority.NORMAL)
        assert queue.size() == 1
