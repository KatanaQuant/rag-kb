"""
TDD Tests for Post-Indexing Orphan Detection

Issue #2 in KNOWN_ISSUES.md:
Orphan files created *during* initial indexing aren't caught by startup sanitization
because sanitization runs BEFORE indexing begins.

Fix: Add orphan detection AFTER indexing completes.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestPostIndexingOrphanCheck:
    """Test that orphan detection runs after initial indexing completes"""

    @patch('startup.manager.OrphanDetector')
    @patch('startup.manager.SelfHealingService')
    def test_background_task_checks_orphans_after_indexing(
        self, mock_healer_class, mock_detector_class
    ):
        """After _index_docs completes, orphan detection should run again

        This catches orphans created during initial indexing that were
        missed by the pre-indexing sanitization stage.
        """
        from startup.manager import StartupManager
        from app_state import AppState

        # Setup mocks
        mock_detector = Mock()
        mock_detector.detect_orphans.return_value = []  # No orphans
        mock_detector_class.return_value = mock_detector

        mock_healer = Mock()
        mock_healer_class.return_value = mock_healer

        # Create manager with mocked state
        state = AppState()
        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing.queue = Mock()

        manager = StartupManager(state)

        # Mock internal methods to isolate test
        manager._start_watcher = Mock()
        manager._sanitize_before_indexing = Mock()
        manager._index_docs = Mock()

        # Run background task
        manager._background_indexing_task()

        # Verify: _check_post_indexing_orphans should be called
        # This is the NEW method we need to implement
        assert hasattr(manager, '_check_post_indexing_orphans'), \
            "StartupManager should have _check_post_indexing_orphans method"

    def test_post_indexing_orphan_check_queues_found_orphans(self):
        """If orphans are found after indexing, they should be queued for repair"""
        from startup.manager import StartupManager
        from app_state import AppState

        state = AppState()
        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing.queue = Mock()

        manager = StartupManager(state)

        # Mock OrphanDetector to return some orphans
        with patch('startup.manager.OrphanDetector') as mock_detector_class:
            mock_detector = Mock()
            mock_detector.detect_orphans.return_value = [
                '/path/to/orphan1.pdf',
                '/path/to/orphan2.md'
            ]
            mock_detector_class.return_value = mock_detector

            # Call the post-indexing check
            manager._check_post_indexing_orphans()

            # Verify orphans were detected
            mock_detector.detect_orphans.assert_called_once()

            # Verify repair was triggered (queues orphans)
            mock_detector.repair_orphans.assert_called_once_with(state.indexing.queue)

    def test_post_indexing_orphan_check_logs_when_no_orphans(self, capsys):
        """When no orphans found after indexing, log success message"""
        from startup.manager import StartupManager
        from app_state import AppState

        state = AppState()
        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing.queue = Mock()

        manager = StartupManager(state)

        # Mock OrphanDetector to return no orphans
        with patch('startup.manager.OrphanDetector') as mock_detector_class:
            mock_detector = Mock()
            mock_detector.detect_orphans.return_value = []
            mock_detector_class.return_value = mock_detector

            # Call the post-indexing check
            manager._check_post_indexing_orphans()

            # Verify appropriate log message
            captured = capsys.readouterr()
            assert "post-indexing" in captured.out.lower() or "no orphans" in captured.out.lower()

    def test_post_indexing_check_respects_auto_repair_setting(self):
        """Post-indexing orphan check should respect AUTO_REPAIR_ORPHANS env var"""
        from startup.manager import StartupManager
        from app_state import AppState
        import os

        state = AppState()
        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing.queue = Mock()

        manager = StartupManager(state)

        # Disable auto-repair
        with patch.dict(os.environ, {'AUTO_REPAIR_ORPHANS': 'false'}):
            with patch('startup.manager.OrphanDetector') as mock_detector_class:
                mock_detector = Mock()
                mock_detector_class.return_value = mock_detector

                manager._check_post_indexing_orphans()

                # OrphanDetector should NOT be instantiated when disabled
                mock_detector.detect_orphans.assert_not_called()


class TestBackgroundIndexingTaskFlow:
    """Test the complete flow of background indexing task"""

    def test_background_task_calls_post_indexing_orphan_check(self):
        """_background_indexing_task should call _check_post_indexing_orphans after _index_docs"""
        from startup.manager import StartupManager
        from app_state import AppState

        state = AppState()
        state.core.progress_tracker = Mock()
        state.core.vector_store = Mock()
        state.indexing.queue = Mock()
        state.runtime.indexing_in_progress = False

        manager = StartupManager(state)

        # Track call order
        call_order = []

        def track_start_watcher():
            call_order.append('start_watcher')

        def track_sanitize():
            call_order.append('sanitize')

        def track_index():
            call_order.append('index_docs')

        def track_post_orphan():
            call_order.append('post_indexing_orphans')

        manager._start_watcher = track_start_watcher
        manager._sanitize_before_indexing = track_sanitize
        manager._index_docs = track_index
        manager._check_post_indexing_orphans = track_post_orphan

        # Run background task
        manager._background_indexing_task()

        # Verify order: watcher → sanitize → index → post-indexing orphan check
        assert call_order == [
            'start_watcher',
            'sanitize',
            'index_docs',
            'post_indexing_orphans'
        ], f"Expected order not met. Got: {call_order}"
