"""Indexing worker service for processing files from queue.

Principles:
- Single Responsibility: Route files from queue to pipeline
- Dependency Injection: queue and pipeline_coordinator injected
- Small class: < 100 lines
- Few instance variables: 3
"""

import threading
import time
from typing import Optional
from pathlib import Path

class IndexingWorker:
    """Routes files from indexing queue to concurrent pipeline

    Runs in background thread, consuming from queue and routing to pipeline.
    """

    def __init__(self, queue, indexer, pipeline_coordinator):
        self.queue = queue
        self.pipeline_coordinator = pipeline_coordinator
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

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
        """Main work loop - processes items from queue"""
        try:
            while self.running:
                try:
                    item = self.queue.get(timeout=1.0)
                    if item:
                        self._process_item(item)
                    else:
                        # Queue empty or paused, sleep briefly
                        time.sleep(0.1)
                except Exception as e:
                    import traceback
                    print(f"[IndexingWorker] Error in work loop: {e}")
                    traceback.print_exc()
                    # Continue running unless fatal
        except Exception as e:
            import traceback
            print(f"[IndexingWorker] FATAL: Thread exiting due to: {e}")
            traceback.print_exc()

    def _process_item(self, item):
        """Route a single queue item to the pipeline"""
        try:
            self.pipeline_coordinator.add_file(item)
        except Exception as e:
            print(f"Worker error routing {item.path}: {e}")

    def is_running(self) -> bool:
        """Check if worker is running"""
        with self._lock:
            return self.running
