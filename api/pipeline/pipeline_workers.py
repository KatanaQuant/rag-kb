# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Pipeline workers for concurrent processing stages.

Follows Sandi Metz OOP principles:
- Single Responsibility: Each worker handles one pipeline stage
- Dependency Injection: Queues and processing functions injected
- Small classes: < 100 lines each
"""

import threading
import time
from typing import Callable, List, Optional
from queue import Empty
from pathlib import Path

from pipeline.pipeline_queues import ExtractedDocument, ChunkedDocument, EmbeddedDocument

class StageWorker:
    """Generic worker for a pipeline stage

    Processes items from input queue and puts results in output queue.
    """

    def __init__(self, name: str, input_queue, output_queue, process_fn: Callable):
        self.name = name
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.process_fn = process_fn
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._current_item: Optional[str] = None
        self._processing = False  # Track if actively processing

    def start(self):
        """Start worker thread"""
        with self._lock:
            if self.running:
                return
            self.running = True
            self._thread = threading.Thread(target=self._work_loop, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop worker thread"""
        with self._lock:
            self.running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _work_loop(self):
        """Main work loop"""
        while self.running:
            try:
                item = self.input_queue.get(timeout=1.0)
                self._process_item(item)
            except Empty:
                self._handle_empty_queue()
            except Exception as e:
                self._handle_processing_error(e)

    def _process_item(self, item):
        """Process a single work item"""
        self._set_processing_state(item, True)
        result = self.process_fn(item)
        self._send_result_if_exists(result)
        self._set_processing_complete()

    def _set_processing_state(self, item, processing: bool):
        """Update processing state with lock"""
        with self._lock:
            self._current_item = str(item.path.name) if hasattr(item, 'path') else str(item)
            self._processing = processing

    def _send_result_if_exists(self, result):
        """Send result to output queue if result exists and queue is available"""
        if result and self.output_queue:
            self.output_queue.put(result)

    def _set_processing_complete(self):
        """Mark processing as complete (keep current_item for monitoring)"""
        with self._lock:
            self._processing = False

    def _handle_empty_queue(self):
        """Handle empty queue timeout"""
        with self._lock:
            if not self._processing:
                self._current_item = None

    def _handle_processing_error(self, exception):
        """Handle processing error"""
        print(f"{self.name} error: {exception}")
        with self._lock:
            self._current_item = None
            self._processing = False

    def get_current_item(self) -> Optional[str]:
        """Get currently processing item (for monitoring)"""
        with self._lock:
            return self._current_item

    def is_running(self) -> bool:
        """Check if worker is running"""
        with self._lock:
            return self.running

class EmbedWorkerPool:
    """Pool of embedding workers (the bottleneck)

    Runs multiple workers in parallel to maximize CPU utilization.
    """

    def __init__(self, num_workers: int, input_queue, output_queue, embed_fn):
        self.workers = [
            StageWorker(
                name=f"EmbedWorker-{i}",
                input_queue=input_queue,
                output_queue=output_queue,
                process_fn=embed_fn
            )
            for i in range(num_workers)
        ]

    def start(self):
        """Start all workers"""
        for worker in self.workers:
            worker.start()

    def stop(self):
        """Stop all workers"""
        for worker in self.workers:
            worker.stop()

    def get_active_jobs(self) -> List[str]:
        """Get list of files currently being embedded"""
        return [
            item
            for worker in self.workers
            if (item := worker.get_current_item())
        ]

    def is_running(self) -> bool:
        """Check if any worker is running"""
        return any(worker.is_running() for worker in self.workers)
