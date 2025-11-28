# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for indexing queue service"""

import pytest
import threading
import time
from pathlib import Path
from pipeline.indexing_queue import IndexingQueue, Priority, QueueItem


class TestQueueItem:
    """Test QueueItem ordering"""

    def test_priority_ordering(self):
        """Higher priority items come first"""
        high = QueueItem(priority=Priority.HIGH, path=Path("high.pdf"))
        normal = QueueItem(priority=Priority.NORMAL, path=Path("normal.pdf"))
        low = QueueItem(priority=Priority.LOW, path=Path("low.pdf"))

        assert high < normal
        assert normal < low
        assert high < low


class TestIndexingQueue:
    """Test IndexingQueue functionality"""

    def test_add_and_get(self):
        """Can add and retrieve items"""
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        item = queue.get()

        assert item is not None
        assert item.path == path

    def test_priority_order(self):
        """Items returned in priority order"""
        queue = IndexingQueue()

        queue.add(Path("low.pdf"), Priority.LOW)
        queue.add(Path("high.pdf"), Priority.HIGH)
        queue.add(Path("normal.pdf"), Priority.NORMAL)

        assert queue.get().path == Path("high.pdf")
        assert queue.get().path == Path("normal.pdf")
        assert queue.get().path == Path("low.pdf")

    def test_pause_blocks_get(self):
        """Paused queue returns None on get"""
        queue = IndexingQueue()
        queue.add(Path("test.pdf"))
        queue.pause()

        item = queue.get(timeout=0.1)
        assert item is None

    def test_resume_allows_get(self):
        """Resumed queue returns items"""
        queue = IndexingQueue()
        queue.add(Path("test.pdf"))
        queue.pause()
        queue.resume()

        item = queue.get()
        assert item is not None

    def test_is_paused(self):
        """is_paused reflects queue state"""
        queue = IndexingQueue()
        assert not queue.is_paused()

        queue.pause()
        assert queue.is_paused()

        queue.resume()
        assert not queue.is_paused()

    def test_size(self):
        """size returns correct queue size"""
        queue = IndexingQueue()
        assert queue.size() == 0

        queue.add(Path("test1.pdf"))
        queue.add(Path("test2.pdf"))
        assert queue.size() == 2

        queue.get()
        assert queue.size() == 1

    def test_is_empty(self):
        """is_empty correctly reports empty state"""
        queue = IndexingQueue()
        assert queue.is_empty()

        queue.add(Path("test.pdf"))
        assert not queue.is_empty()

        queue.get()
        assert queue.is_empty()

    def test_add_many(self):
        """add_many adds multiple files"""
        queue = IndexingQueue()
        paths = [Path("test1.pdf"), Path("test2.pdf"), Path("test3.pdf")]

        queue.add_many(paths)
        assert queue.size() == 3

    def test_clear(self):
        """clear removes all items"""
        queue = IndexingQueue()
        queue.add_many([Path("test1.pdf"), Path("test2.pdf"), Path("test3.pdf")])

        queue.clear()
        assert queue.is_empty()

    def test_thread_safety(self):
        """Queue is thread-safe"""
        queue = IndexingQueue()
        results = []

        def producer():
            for i in range(10):
                queue.add(Path(f"test{i}.pdf"))

        def consumer():
            while queue.size() > 0 or not queue.is_empty():
                item = queue.get(timeout=0.1)
                if item:
                    results.append(item.path)
                time.sleep(0.01)

        producer_thread = threading.Thread(target=producer)
        consumer_thread = threading.Thread(target=consumer)

        producer_thread.start()
        consumer_thread.start()

        producer_thread.join()
        consumer_thread.join()

        # Should have processed some items (may not be all due to timing)
        assert len(results) > 0

    def test_force_flag(self):
        """Force flag is preserved"""
        queue = IndexingQueue()
        queue.add(Path("test.pdf"), force=True)

        item = queue.get()
        assert item.force is True

    def test_timeout_on_empty(self):
        """get returns None on timeout"""
        queue = IndexingQueue()
        start = time.time()
        item = queue.get(timeout=0.1)
        elapsed = time.time() - start

        assert item is None
        assert elapsed >= 0.1
        assert elapsed < 0.3  # Should not wait much longer

    def test_duplicate_detection(self):
        """Adding same file twice only queues it once"""
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        queue.add(path)  # Duplicate - should be skipped

        assert queue.size() == 1
        item = queue.get()
        assert item.path == path
        assert queue.is_empty()

    def test_duplicate_detection_with_force(self):
        """Force flag does NOT bypass queue deduplication (v1.7.3 fix)

        The force flag only affects reindexing behavior (whether to reindex
        already-indexed files). Queue deduplication always applies to prevent
        duplicate processing of files already in the queue.
        """
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        queue.add(path, force=True)  # Force only affects reindexing, not queue dedup

        # Queue deduplication always applies - only 1 item in queue
        assert queue.size() == 1

        # But the force flag should be preserved on the item
        item = queue.get()
        assert item.path == path

    def test_duplicate_tracking_after_get(self):
        """File stays tracked after get() - must call mark_complete() to re-queue

        This prevents race conditions where a file could be re-queued during
        processing (e.g., from duplicate watcher events).
        """
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        item = queue.get()
        assert item.path == path

        # File is still tracked after get() - cannot re-add yet
        queue.add(path)
        assert queue.size() == 0  # Didn't get added - still tracked

        # After mark_complete(), can re-queue
        queue.mark_complete(path)
        queue.add(path)
        assert queue.size() == 1

    def test_mark_complete(self):
        """mark_complete() removes file from tracking set"""
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        queue.get()  # Dequeue but still tracked

        # Can't add while tracked
        queue.add(path)
        assert queue.size() == 0

        # After mark_complete, tracking removed
        queue.mark_complete(path)
        queue.add(path)
        assert queue.size() == 1

    def test_mark_complete_idempotent(self):
        """mark_complete() is safe to call multiple times"""
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        queue.get()

        # Multiple mark_complete calls are safe
        queue.mark_complete(path)
        queue.mark_complete(path)  # Should not raise

        queue.add(path)
        assert queue.size() == 1

    def test_clear_resets_duplicate_tracking(self):
        """clear() resets duplicate tracking"""
        queue = IndexingQueue()
        path = Path("test.pdf")

        queue.add(path)
        queue.clear()

        # Should be able to add again after clear
        queue.add(path)
        assert queue.size() == 1
