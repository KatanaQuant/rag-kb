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
