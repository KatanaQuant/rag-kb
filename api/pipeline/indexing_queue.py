# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Indexing queue service for managing document processing with priorities.

Follows Sandi Metz OOP principles:
- Single Responsibility: Queue management only
- Dependency Injection: No hardcoded dependencies
- Small classes: < 100 lines
- Few instance variables: < 4
"""

import threading
from pathlib import Path
from queue import PriorityQueue, Empty
from dataclasses import dataclass, field
from typing import Optional, List
from enum import IntEnum

class Priority(IntEnum):
    """Priority levels for indexing queue"""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0

@dataclass(order=True)
class QueueItem:
    """Item in indexing queue with priority support"""
    priority: int
    path: Path = field(compare=False)
    force: bool = field(default=False, compare=False)

class IndexingQueue:
    """Priority queue for document indexing with pause/resume support

    Thread-safe implementation using PriorityQueue with duplicate detection.
    Tracks queued files to prevent duplicate processing.

    Follows Sandi Metz rules:
    - < 100 lines
    - 4 instance variables
    - Methods < 5 lines (mostly)
    """

    def __init__(self):
        self.queue = PriorityQueue()
        self.paused = False
        self.lock = threading.Lock()
        self.queued_files: set[Path] = set()  # Track files currently in queue

    def add(self, path: Path, priority: Priority = Priority.NORMAL, force: bool = False):
        """Add file to queue with priority (skip if already queued)

        Args:
            path: File path to queue
            priority: Queue priority (HIGH, NORMAL, LOW)
            force: If True, force reprocessing even if already indexed.
                   Does NOT bypass duplicate queue check - files already
                   in queue are always skipped to prevent duplicate processing.
        """
        with self.lock:
            # Always check if already queued - prevent duplicate processing
            # This check is independent of force flag (force is for reindexing,
            # not for bypassing queue deduplication)
            if path in self.queued_files:
                return  # Silent skip - already queued

            self.queued_files.add(path)

        item = QueueItem(priority=priority.value, path=path, force=force)
        self.queue.put(item)

    def add_many(self, paths: List[Path], priority: Priority = Priority.NORMAL, force: bool = False):
        """Add multiple files to queue"""
        for path in paths:
            self.add(path, priority, force=force)

    def get(self, timeout: float = 1.0) -> Optional[QueueItem]:
        """Get next item from queue (respects pause state)

        Returns None if paused or queue empty.
        Blocks for up to timeout seconds if queue not empty.
        Note: File stays in queued_files until mark_complete() is called.
        """
        with self.lock:
            if self.paused:
                return None

        try:
            item = self.queue.get(timeout=timeout)
            # Don't remove from queued_files here - wait for mark_complete()
            # This prevents race conditions where a file is re-queued during processing
            return item
        except Empty:
            return None

    def mark_complete(self, path: Path):
        """Mark file as complete - removes from tracking set

        Call this after a file has been fully processed (stored in DB).
        This prevents race conditions where duplicate watcher events
        could re-queue a file that's still being processed.
        """
        with self.lock:
            self.queued_files.discard(path)

    def pause(self):
        """Pause queue processing"""
        with self.lock:
            self.paused = True

    def resume(self):
        """Resume queue processing"""
        with self.lock:
            self.paused = False

    def is_paused(self) -> bool:
        """Check if queue is paused"""
        with self.lock:
            return self.paused

    def size(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()

    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self.queue.empty()

    def clear(self):
        """Clear all items from queue and tracking set"""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Empty:
                break

        with self.lock:
            self.queued_files.clear()
