# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Batch logger for skip events during indexing.

Reduces log noise by batching skip messages and printing periodic summaries
instead of individual "[Skip] file.pdf - already indexed" for every file.

Following Sandi Metz POODR principles:
- Single Responsibility: Batch skip logging only
- Small methods: Each method <10 lines
- Thread-safe: Uses locks for concurrent access
"""

import threading
import time
from typing import Optional
from collections import defaultdict


class SkipBatcher:
    """Batches skip events and prints periodic summaries

    Usage:
        batcher = SkipBatcher(interval=10)  # Print every 10 seconds
        batcher.start()

        # During processing
        batcher.record_skip("file.pdf", "already indexed")

        # When done
        batcher.stop()  # Prints final summary
    """

    def __init__(self, interval: float = 10.0, time_source=None):
        """Initialize batcher

        Args:
            interval: Seconds between summary prints (default: 10)
            time_source: Injectable time source for testing
        """
        self.interval = interval
        self.time_source = time_source or time.time

        self._lock = threading.Lock()
        self._skips: dict = defaultdict(int)  # reason -> count
        self._total_skipped = 0
        self._last_printed_count = 0  # Track what we last printed

        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the periodic summary thread"""
        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._summary_worker,
            daemon=True
        )
        self._thread.start()

    def stop(self):
        """Stop the summary thread and print final summary"""
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._print_final_summary()

    def record_skip(self, filename: str, reason: str):
        """Record a skip event

        Args:
            filename: Name of skipped file (for potential verbose mode)
            reason: Reason for skip (e.g., "already indexed")
        """
        with self._lock:
            self._skips[reason] += 1
            self._total_skipped += 1

    def _summary_worker(self):
        """Worker thread that prints periodic summaries"""
        while not self._stop_flag.wait(self.interval):
            self._print_summary_if_needed()

    def _print_summary_if_needed(self):
        """Print summary if there are new skips since last print"""
        with self._lock:
            if self._total_skipped == 0:
                return

            # Only print if we have NEW skips since last print
            if self._total_skipped > self._last_printed_count:
                self._print_current_summary()
                self._last_printed_count = self._total_skipped

    def _print_current_summary(self):
        """Print current skip summary (called with lock held)"""
        if not self._skips:
            return

        parts = [f"[Skip] {self._total_skipped} files skipped"]
        breakdown = ", ".join(f"{count} {reason}" for reason, count in self._skips.items())
        if breakdown:
            parts.append(f"({breakdown})")

        print(" ".join(parts))

    def _print_final_summary(self):
        """Print final summary when stopping"""
        with self._lock:
            if self._total_skipped == 0:
                return

            print(f"[Skip] Total: {self._total_skipped} files skipped")
            for reason, count in sorted(self._skips.items(), key=lambda x: -x[1]):
                print(f"       - {count} {reason}")

    def get_stats(self) -> dict:
        """Get current skip statistics"""
        with self._lock:
            return {
                'total_skipped': self._total_skipped,
                'by_reason': dict(self._skips)
            }

    def reset(self):
        """Reset counters (for testing or new batch)"""
        with self._lock:
            self._skips.clear()
            self._total_skipped = 0
            self._last_printed_count = 0


# Singleton instance for global use
_default_batcher: Optional[SkipBatcher] = None


def get_skip_batcher() -> SkipBatcher:
    """Get or create the default skip batcher"""
    global _default_batcher
    if _default_batcher is None:
        _default_batcher = SkipBatcher()
    return _default_batcher
