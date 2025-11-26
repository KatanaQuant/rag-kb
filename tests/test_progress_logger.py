# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for ProgressLogger - TDD approach

Following Sandi Metz POODR principles:
- Single Responsibility: Progress logging only
- Duck typing: Works with any stage
- Small, focused tests
"""

import pytest
import time
from io import StringIO
import sys


class TestProgressLogger:
    """Test suite for ProgressLogger"""

    def setup_method(self):
        """Set up test fixtures"""
        # Import here to avoid circular dependencies during test discovery
        from pipeline.progress_logger import ProgressLogger
        self.logger = ProgressLogger()

    def teardown_method(self):
        """Clean up after each test to prevent thread leakage"""
        # Stop all heartbeat threads
        for key in list(self.logger.heartbeat_stop_flags.keys()):
            self.logger._stop_heartbeat(key)

    def test_log_start_message(self, capsys):
        """Starting a stage should log stage and document name"""
        self.logger.log_start("Chunk", "example.pdf")
        captured = capsys.readouterr()
        assert "[Chunk] example.pdf" in captured.out

    def test_log_progress_with_counts(self, capsys):
        """Progress should show current/total and percentage"""
        self.logger.log_progress("Embed", "example.pdf", current=5, total=10)
        captured = capsys.readouterr()

        assert "[Embed] example.pdf" in captured.out
        assert "5/10" in captured.out
        assert "50%" in captured.out

    def test_log_progress_with_time_tracking(self, capsys):
        """Progress should include elapsed time"""
        self.logger.log_start("Embed", "example.pdf")
        time.sleep(0.1)  # Simulate some work
        self.logger.log_progress("Embed", "example.pdf", current=5, total=10)
        captured = capsys.readouterr()

        # Should show elapsed time (0.1s+)
        assert "0." in captured.out  # Contains decimal seconds
        assert "s" in captured.out  # Shows seconds unit

    def test_log_progress_shows_rate(self, capsys):
        """Progress should show processing rate (items/sec)"""
        self.logger.log_start("Embed", "example.pdf")
        time.sleep(0.2)  # Simulate work
        self.logger.log_progress("Embed", "example.pdf", current=10, total=20)
        captured = capsys.readouterr()

        # Should show rate (10 items in 0.2s = ~50 items/s)
        assert "chunks/s" in captured.out or "items/s" in captured.out

    def test_log_complete_message(self, capsys):
        """Completion should show final stats"""
        self.logger.log_start("Store", "example.pdf")
        time.sleep(0.1)
        self.logger.log_complete("Store", "example.pdf", total=100)
        captured = capsys.readouterr()

        assert "[Store] example.pdf" in captured.out
        assert "100 chunks" in captured.out
        assert "complete" in captured.out.lower()

    def test_multiple_documents_independently_tracked(self, capsys):
        """Each document should have independent timing"""
        self.logger.log_start("Embed", "doc1.pdf")
        time.sleep(0.1)
        self.logger.log_start("Embed", "doc2.pdf")
        time.sleep(0.1)

        self.logger.log_progress("Embed", "doc1.pdf", current=5, total=10)
        captured1 = capsys.readouterr()

        # doc1 should show ~0.2s elapsed (started first)
        assert "[Embed] doc1.pdf" in captured1.out

        self.logger.log_progress("Embed", "doc2.pdf", current=3, total=10)
        captured2 = capsys.readouterr()

        # doc2 should show ~0.1s elapsed (started later)
        assert "[Embed] doc2.pdf" in captured2.out

    def test_log_format_consistency(self, capsys):
        """All logs should follow consistent format: [Stage] Document | Message"""
        self.logger.log_start("Chunk", "test.pdf")
        captured1 = capsys.readouterr()

        self.logger.log_progress("Embed", "test.pdf", current=1, total=5)
        captured2 = capsys.readouterr()

        self.logger.log_complete("Store", "test.pdf", total=5)
        captured3 = capsys.readouterr()

        # All should start with [Stage] Document format
        assert captured1.out.startswith("[Chunk] test.pdf")
        assert "[Embed] test.pdf" in captured2.out
        assert captured3.out.startswith("[Store] test.pdf")

    def test_handles_zero_total_gracefully(self, capsys):
        """Should not crash with zero total"""
        self.logger.log_progress("Embed", "empty.pdf", current=0, total=0)
        captured = capsys.readouterr()

        # Should still log something without division by zero
        assert "[Embed] empty.pdf" in captured.out

    def test_eta_calculation(self, capsys):
        """Progress should show estimated time remaining"""
        self.logger.log_start("Embed", "large.pdf")
        time.sleep(0.2)  # Simulate processing first 25%
        self.logger.log_progress("Embed", "large.pdf", current=25, total=100)
        captured = capsys.readouterr()

        # Should show ETA (roughly 0.6s remaining at current rate)
        assert "ETA" in captured.out or "remaining" in captured.out.lower()

    def test_heartbeat_stops_on_completion(self, capsys):
        """Heartbeat thread should stop when log_complete is called"""
        self.logger.log_start("Chunk", "doc1.pdf")
        self.logger.start_heartbeat("Chunk", "doc1.pdf", interval=1)

        # Let heartbeat run once
        time.sleep(1.5)
        capsys.readouterr()  # Clear buffer

        # Complete the processing
        self.logger.log_complete("Chunk", "doc1.pdf", total=100)
        capsys.readouterr()  # Clear buffer

        # Wait for what would be another heartbeat
        time.sleep(1.5)
        captured = capsys.readouterr()

        # Should NOT see heartbeat message for doc1.pdf
        assert "doc1.pdf - processing..." not in captured.out

    def test_heartbeat_stops_when_new_file_starts_same_stage(self, capsys):
        """When a new file starts in the same stage, old heartbeat should stop"""
        # Start processing first file
        self.logger.log_start("Chunk", "old.pdf")
        self.logger.start_heartbeat("Chunk", "old.pdf", interval=1)

        # Let heartbeat run once
        time.sleep(1.5)
        capsys.readouterr()  # Clear buffer

        # Start processing second file in same stage WITHOUT calling log_complete for first
        self.logger.log_start("Chunk", "new.pdf")
        self.logger.start_heartbeat("Chunk", "new.pdf", interval=1)
        capsys.readouterr()  # Clear buffer

        # Wait for heartbeat interval
        time.sleep(1.5)
        captured = capsys.readouterr()

        # Should ONLY see heartbeat for new.pdf, NOT old.pdf
        assert "new.pdf - processing..." in captured.out
        assert "old.pdf - processing..." not in captured.out

    def test_heartbeat_cleanup_prevents_orphaned_threads(self, capsys):
        """Ensure no heartbeat threads are left running after all work is done"""
        # Process multiple files
        for i in range(3):
            filename = f"file{i}.pdf"
            self.logger.log_start("Chunk", filename)
            self.logger.start_heartbeat("Chunk", filename, interval=1)
            time.sleep(0.5)
            self.logger.log_complete("Chunk", filename, total=100)

        capsys.readouterr()  # Clear buffer

        # Wait for what would be heartbeat intervals
        time.sleep(2)
        captured = capsys.readouterr()

        # Should have NO heartbeat messages
        assert "processing..." not in captured.out

        # Verify internal cleanup
        assert len(self.logger.heartbeat_threads) == 0
        assert len(self.logger.heartbeat_stop_flags) == 0

    def test_heartbeat_stops_on_zero_chunks(self, capsys):
        """Heartbeat should stop even when processing yields 0 chunks"""
        self.logger.log_start("Chunk", "empty.go")
        self.logger.start_heartbeat("Chunk", "empty.go", interval=1)

        # Let heartbeat run once
        time.sleep(1.5)
        capsys.readouterr()  # Clear buffer

        # Complete with 0 chunks (simulates files with no extractable content)
        self.logger.log_complete("Chunk", "empty.go", total=0)
        capsys.readouterr()  # Clear buffer

        # Wait for what would be another heartbeat
        time.sleep(1.5)
        captured = capsys.readouterr()

        # Should NOT see heartbeat message for empty.go
        assert "empty.go - processing..." not in captured.out

        # Verify cleanup
        assert len(self.logger.heartbeat_threads) == 0
        assert len(self.logger.heartbeat_stop_flags) == 0
