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

    Thread-safe implementation using PriorityQueue.
    Follows Sandi Metz rules:
    - < 100 lines
    - 3 instance variables
    - Methods < 5 lines (mostly)
    """

    def __init__(self):
        self.queue = PriorityQueue()
        self.paused = False
        self.lock = threading.Lock()

    def add(self, path: Path, priority: Priority = Priority.NORMAL, force: bool = False):
        """Add file to queue with priority"""
        item = QueueItem(priority=priority.value, path=path, force=force)
        self.queue.put(item)

    def add_many(self, paths: List[Path], priority: Priority = Priority.NORMAL):
        """Add multiple files to queue"""
        for path in paths:
            self.add(path, priority)

    def get(self, timeout: float = 1.0) -> Optional[QueueItem]:
        """Get next item from queue (respects pause state)

        Returns None if paused or queue empty.
        Blocks for up to timeout seconds if queue not empty.
        """
        with self.lock:
            if self.paused:
                return None

        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None

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
        """Clear all items from queue"""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Empty:
                break
