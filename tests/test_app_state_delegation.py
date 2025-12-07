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

    def test_stop_watcher_handles_none(self, state):
        """stop_watcher() should handle None watcher gracefully"""
        state.runtime.watcher = None
        state.stop_watcher()  # Should not raise

    def test_stop_indexing_handles_none(self, state):
        """stop_indexing() should handle None worker gracefully"""
        state.indexing.worker = None
        state.stop_indexing()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_vector_store_handles_none(self, state):
        """close_vector_store() should handle None gracefully"""
        state.core.vector_store = None
        await state.close_vector_store()  # Should not raise

    def test_close_progress_tracker_handles_none(self, state):
        """close_progress_tracker() should handle None gracefully"""
        state.core.progress_tracker = None
        state.close_progress_tracker()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_all_resources(self, state):
        """AppState.close_all_resources() should close all resources"""
        await state.close_all_resources()

        state.core.vector_store.close.assert_called_once()
        state.core.progress_tracker.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_vector_store_stats_delegates(self, state):
        """AppState.get_vector_store_stats() should delegate and return stats (async)"""
        from unittest.mock import AsyncMock

        # Mock async get_stats method
        async def mock_get_stats():
            return {'docs': 42, 'chunks': 1337}

        state.core.async_vector_store = Mock()
        state.core.async_vector_store.get_stats = AsyncMock(side_effect=mock_get_stats)

        stats = await state.get_vector_store_stats()

        assert stats == {'docs': 42, 'chunks': 1337}
        state.core.async_vector_store.get_stats.assert_called_once()

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
