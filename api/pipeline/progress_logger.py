"""Progress logging with time tracking for pipeline stages.

Principles:
- Single Responsibility: Progress logging only
- Small methods: Each method <10 lines
- Duck typing: Works with any stage name
- Dependency injection: Can inject time source for testing
"""

import time
import threading
from typing import Dict, Optional


class ProgressLogger:
    """Logs progress with timing and context for pipeline stages

    Tracks progress across multiple documents independently with:
    - Document name and stage
    - Progress (current/total, percentage)
    - Timing (elapsed, rate, ETA)
    - Consistent format: [Stage] Document | Message
    """

    def __init__(self, time_source=None):
        """Initialize logger with optional time source for testing"""
        self.time_source = time_source or time.time
        self.start_times: Dict[str, float] = {}
        self.heartbeat_threads: Dict[str, threading.Thread] = {}
        self.heartbeat_stop_flags: Dict[str, threading.Event] = {}

    def log_start(self, stage: str, document: str):
        """Log stage start and record start time"""
        key = self._make_key(stage, document)
        self.start_times[key] = self.time_source()
        print(f"[{stage}] {document}")

    def log_progress(self, stage: str, document: str, current: int, total: int):
        """Log progress with percentage, elapsed time, rate, and ETA"""
        if total == 0:
            print(f"[{stage}] {document} - no chunks to process")
            return

        key = self._make_key(stage, document)
        elapsed = self._elapsed(key)
        percentage = self._percentage(current, total)
        rate = self._rate(current, elapsed)
        eta = self._eta(current, total, rate)

        print(f"[{stage}] {document} | {current}/{total} ({percentage}%) | "
              f"{elapsed:.1f}s elapsed | {rate:.1f} chunks/s | ETA: {eta:.1f}s")

    def log_complete(self, stage: str, document: str, total: int, start_time: float = None):
        """Log completion with final stats

        Args:
            stage: Pipeline stage name
            document: Document name
            total: Total chunks processed
            start_time: Optional explicit start time (for accurate timing when
                        log_start wasn't called or extraction took significant time)
        """
        key = self._make_key(stage, document)
        if start_time is not None:
            elapsed = self.time_source() - start_time
        else:
            elapsed = self._elapsed(key)
        rate = self._rate(total, elapsed)

        print(f"[{stage}] {document} - {total} chunks complete in {elapsed:.1f}s ({rate:.1f} chunks/s)")
        self._cleanup(key)

    def _make_key(self, stage: str, document: str) -> str:
        """Create unique key for tracking"""
        return f"{stage}:{document}"

    def _elapsed(self, key: str) -> float:
        """Calculate elapsed time"""
        start = self.start_times.get(key, self.time_source())
        return self.time_source() - start

    def _percentage(self, current: int, total: int) -> int:
        """Calculate percentage complete"""
        return int((current / total) * 100) if total > 0 else 0

    def _rate(self, items: int, elapsed: float) -> float:
        """Calculate processing rate"""
        return items / elapsed if elapsed > 0 else 0.0

    def _eta(self, current: int, total: int, rate: float) -> float:
        """Calculate estimated time remaining"""
        remaining = total - current
        return remaining / rate if rate > 0 else 0.0

    def _cleanup(self, key: str):
        """Remove completed tracking entry"""
        self.start_times.pop(key, None)
        self._stop_heartbeat(key)

    def start_heartbeat(self, stage: str, document: str, interval: int = 60):
        """Start periodic heartbeat logging for long-running operations"""
        # Stop all existing heartbeats for this stage to prevent orphaned threads
        # (Only one file per stage is processed at a time)
        self._stop_all_heartbeats_for_stage(stage)

        key = self._make_key(stage, document)

        # Create stop flag
        stop_flag = threading.Event()
        self.heartbeat_stop_flags[key] = stop_flag

        # Create and start heartbeat thread
        thread = threading.Thread(
            target=self._heartbeat_worker,
            args=(stage, document, interval, stop_flag),
            daemon=True
        )
        self.heartbeat_threads[key] = thread
        thread.start()

    def _heartbeat_worker(self, stage: str, document: str, interval: int, stop_flag: threading.Event):
        """Worker function for heartbeat thread"""
        key = self._make_key(stage, document)

        while not stop_flag.wait(interval):
            # Check again after wait to avoid race condition
            if stop_flag.is_set():
                break
            elapsed = self._elapsed(key)
            print(f"[{stage}] {document} - processing... {elapsed:.0f}s elapsed")

    def _stop_heartbeat(self, key: str):
        """Stop heartbeat thread for given key"""
        if key in self.heartbeat_stop_flags:
            self.heartbeat_stop_flags[key].set()
            if key in self.heartbeat_threads:
                self.heartbeat_threads[key].join(timeout=1)
            self.heartbeat_stop_flags.pop(key, None)
            self.heartbeat_threads.pop(key, None)

    def _stop_all_heartbeats_for_stage(self, stage: str):
        """Stop all heartbeat threads for a given stage"""
        # Find all keys matching this stage (convert to list to avoid dict mutation issues)
        keys_to_stop = [
            key for key in list(self.heartbeat_threads.keys())
            if key.startswith(f"{stage}:")
        ]

        # Stop each matching heartbeat
        for key in keys_to_stop:
            self._stop_heartbeat(key)
