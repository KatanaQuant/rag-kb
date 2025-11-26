"""
Tests for SkipBatcher

Tests the batch logging functionality for skip events.
"""
import pytest
import time
from unittest.mock import Mock, patch


class TestSkipBatcher:
    """Test SkipBatcher batch logging"""

    def test_records_skip_events(self):
        """SkipBatcher should record skip events"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=10)  # Long interval, no auto-print
        batcher.record_skip("file1.pdf", "already indexed")
        batcher.record_skip("file2.pdf", "already indexed")
        batcher.record_skip("file3.md", "unsupported")

        stats = batcher.get_stats()
        assert stats['total_skipped'] == 3
        assert stats['by_reason']['already indexed'] == 2
        assert stats['by_reason']['unsupported'] == 1

    def test_reset_clears_counters(self):
        """SkipBatcher.reset should clear all counters"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher()
        batcher.record_skip("file1.pdf", "already indexed")
        batcher.reset()

        stats = batcher.get_stats()
        assert stats['total_skipped'] == 0
        assert stats['by_reason'] == {}

    def test_thread_safety(self):
        """SkipBatcher should be thread-safe"""
        from services.skip_batcher import SkipBatcher
        import threading

        batcher = SkipBatcher(interval=10)
        errors = []

        def record_many():
            try:
                for i in range(100):
                    batcher.record_skip(f"file{i}.pdf", "already indexed")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert batcher.get_stats()['total_skipped'] == 500

    def test_stop_prints_final_summary(self, capsys):
        """SkipBatcher.stop should print final summary"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=100)  # Very long interval
        batcher.record_skip("file1.pdf", "already indexed")
        batcher.record_skip("file2.pdf", "already indexed")
        batcher.stop()

        captured = capsys.readouterr()
        assert "Total: 2 files skipped" in captured.out
        assert "already indexed" in captured.out

    def test_no_output_when_no_skips(self, capsys):
        """SkipBatcher should not print if no skips recorded"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=100)
        batcher.stop()

        captured = capsys.readouterr()
        assert captured.out == ""


class TestSkipBatcherDefaults:
    """Test SkipBatcher default configuration"""

    def test_default_interval_is_10_seconds(self):
        """SkipBatcher default interval should be 10 seconds"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher()
        assert batcher.interval == 10.0

    def test_custom_interval_overrides_default(self):
        """SkipBatcher should accept custom interval"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=30.0)
        assert batcher.interval == 30.0


class TestSkipBatcherOnlyPrintNew:
    """Test SkipBatcher only prints when NEW skips occur"""

    def test_tracks_last_printed_count(self):
        """SkipBatcher should track last printed count"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=100)  # Long interval to prevent auto-print
        assert batcher._last_printed_count == 0

    def test_reset_clears_last_printed_count(self):
        """SkipBatcher.reset should clear last printed count"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=100)
        batcher._last_printed_count = 10
        batcher.reset()

        assert batcher._last_printed_count == 0

    def test_only_prints_when_new_skips(self, capsys):
        """SkipBatcher should only print when there are new skips"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=100)
        batcher.record_skip("file1.pdf", "already indexed")
        batcher.record_skip("file2.pdf", "already indexed")

        # First print should output
        batcher._print_summary_if_needed()
        captured1 = capsys.readouterr()
        assert "2 files skipped" in captured1.out

        # Second print without new skips should NOT output
        batcher._print_summary_if_needed()
        captured2 = capsys.readouterr()
        assert captured2.out == ""

        # Third print with new skip SHOULD output
        batcher.record_skip("file3.pdf", "already indexed")
        batcher._print_summary_if_needed()
        captured3 = capsys.readouterr()
        assert "3 files skipped" in captured3.out

    def test_no_print_when_zero_skips(self, capsys):
        """SkipBatcher should not print when no skips recorded"""
        from services.skip_batcher import SkipBatcher

        batcher = SkipBatcher(interval=100)
        batcher._print_summary_if_needed()

        captured = capsys.readouterr()
        assert captured.out == ""


class TestSkipBatcherIntegration:
    """Integration tests for SkipBatcher with PipelineCoordinator"""

    def test_pipeline_coordinator_has_skip_batcher(self):
        """PipelineCoordinator should have a skip_batcher attribute"""
        from services.pipeline_coordinator import PipelineCoordinator
        from unittest.mock import Mock

        coordinator = PipelineCoordinator(
            processor=Mock(),
            indexer=Mock(),
            embedding_service=Mock()
        )

        assert hasattr(coordinator, 'skip_batcher')

    def test_pipeline_coordinator_uses_10s_interval(self):
        """PipelineCoordinator should use 10s interval for skip batcher"""
        from services.pipeline_coordinator import PipelineCoordinator
        from unittest.mock import Mock

        coordinator = PipelineCoordinator(
            processor=Mock(),
            indexer=Mock(),
            embedding_service=Mock()
        )

        assert coordinator.skip_batcher.interval == 10.0
