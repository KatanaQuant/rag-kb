"""
Tests for AppState delegation methods

Following TDD: These tests are written BEFORE adding delegation methods
Tests enforce Law of Demeter by hiding internal structure
"""
import pytest
from unittest.mock import Mock
from app_state import AppState


class TestAppStateDelegation:
    """Test AppState delegation methods that hide internal structure"""

    @pytest.fixture
    def state(self):
        """Create AppState with mocked dependencies"""
        state = AppState()
        state.runtime.watcher = Mock()
        state.indexing.worker = Mock()
        state.indexing.queue = Mock()
        state.core.vector_store = Mock()
        state.core.progress_tracker = Mock()
        return state

    def test_stop_watcher_delegates_to_runtime_watcher(self, state):
        """AppState.stop_watcher() should delegate to runtime.watcher.stop()"""
        state.stop_watcher()
        state.runtime.watcher.stop.assert_called_once()

    def test_stop_watcher_handles_none(self, state):
        """stop_watcher() should handle None watcher gracefully"""
        state.runtime.watcher = None
        state.stop_watcher()  # Should not raise

    def test_stop_indexing_delegates_to_worker(self, state):
        """AppState.stop_indexing() should delegate to indexing.worker.stop()"""
        state.stop_indexing()
        state.indexing.worker.stop.assert_called_once()

    def test_stop_indexing_handles_none(self, state):
        """stop_indexing() should handle None worker gracefully"""
        state.indexing.worker = None
        state.stop_indexing()  # Should not raise

    def test_close_vector_store_delegates(self, state):
        """AppState.close_vector_store() should delegate to core.vector_store.close()"""
        state.close_vector_store()
        state.core.vector_store.close.assert_called_once()

    def test_close_vector_store_handles_none(self, state):
        """close_vector_store() should handle None gracefully"""
        state.core.vector_store = None
        state.close_vector_store()  # Should not raise

    def test_close_progress_tracker_delegates(self, state):
        """AppState.close_progress_tracker() should delegate"""
        state.close_progress_tracker()
        state.core.progress_tracker.close.assert_called_once()

    def test_close_progress_tracker_handles_none(self, state):
        """close_progress_tracker() should handle None gracefully"""
        state.core.progress_tracker = None
        state.close_progress_tracker()  # Should not raise

    def test_close_all_resources(self, state):
        """AppState.close_all_resources() should close all resources"""
        state.close_all_resources()

        state.core.vector_store.close.assert_called_once()
        state.core.progress_tracker.close.assert_called_once()

    def test_get_vector_store_stats_delegates(self, state):
        """AppState.get_vector_store_stats() should delegate and return stats"""
        state.core.vector_store.get_stats.return_value = {'docs': 42, 'chunks': 1337}

        stats = state.get_vector_store_stats()

        assert stats == {'docs': 42, 'chunks': 1337}
        state.core.vector_store.get_stats.assert_called_once()

    def test_queue_size_delegates(self, state):
        """AppState.queue_size() should delegate to indexing.queue.size()"""
        state.indexing.queue.size.return_value = 10

        size = state.queue_size()

        assert size == 10
        state.indexing.queue.size.assert_called_once()

    def test_is_queue_paused_delegates(self, state):
        """AppState.is_queue_paused() should delegate"""
        state.indexing.queue.is_paused.return_value = True

        is_paused = state.is_queue_paused()

        assert is_paused == True
        state.indexing.queue.is_paused.assert_called_once()

    def test_is_worker_running_delegates(self, state):
        """AppState.is_worker_running() should delegate"""
        state.indexing.worker.is_running.return_value = True

        is_running = state.is_worker_running()

        assert is_running == True
        state.indexing.worker.is_running.assert_called_once()


class TestLawOfDemeter:
    """Test that delegation methods fix Law of Demeter violations"""

    def test_clients_should_not_reach_through_state(self):
        """
        BAD (LoD violation):
            state.runtime.watcher.stop()

        GOOD (follows LoD):
            state.stop_watcher()

        This test verifies the good pattern works
        """
        state = AppState()
        state.runtime.watcher = Mock()

        # Client code should use delegation method, not reach through
        state.stop_watcher()

        state.runtime.watcher.stop.assert_called_once()
