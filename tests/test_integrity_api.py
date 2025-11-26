"""
Tests for Document Integrity API endpoint

Following TDD - tests written before implementation.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient


class TestIntegrityEndpoint:
    """Test /documents/integrity endpoint"""

    @pytest.fixture
    def mock_app_state(self):
        """Create mock app state with required components"""
        app_state = Mock()
        app_state.core = Mock()
        app_state.core.progress_tracker = Mock()
        app_state.core.async_vector_store = Mock()
        return app_state

    def test_returns_completeness_report(self, mock_app_state):
        """Endpoint should return completeness summary"""
        from operations.completeness_reporter import CompletenessReporter

        # Setup mock data
        mock_app_state.core.progress_tracker.get_progress.return_value = Mock(
            status='completed',
            total_chunks=10,
            chunks_processed=10
        )

        reporter = CompletenessReporter(
            progress_tracker=mock_app_state.core.progress_tracker,
            vector_store=mock_app_state.core.async_vector_store
        )

        # Mock the doc_repo directly
        reporter.doc_repo = Mock()
        reporter.doc_repo.list_all.return_value = [
            {'id': 1, 'file_path': '/test/doc1.pdf'},
            {'id': 2, 'file_path': '/test/doc2.pdf'}
        ]

        # Mock chunk_repo
        reporter.chunk_repo = Mock()
        reporter.chunk_repo.count_by_document.return_value = 10

        result = reporter.generate_report()

        assert 'total_documents' in result
        assert 'complete' in result
        assert 'incomplete' in result
        assert 'issues' in result

    def test_identifies_incomplete_documents(self, mock_app_state):
        """Endpoint should list incomplete documents with reasons"""
        from operations.completeness_reporter import CompletenessReporter

        # One complete, one incomplete (chunk mismatch)
        mock_app_state.core.progress_tracker.get_progress.side_effect = [
            Mock(status='completed', total_chunks=10, chunks_processed=10),
            Mock(status='completed', total_chunks=10, chunks_processed=5)
        ]

        reporter = CompletenessReporter(
            progress_tracker=mock_app_state.core.progress_tracker,
            vector_store=mock_app_state.core.async_vector_store
        )

        # Mock the doc_repo directly
        reporter.doc_repo = Mock()
        reporter.doc_repo.list_all.return_value = [
            {'id': 1, 'file_path': '/test/complete.pdf'},
            {'id': 2, 'file_path': '/test/incomplete.pdf'}
        ]

        # Mock chunk_repo - both have chunks in DB
        reporter.chunk_repo = Mock()
        reporter.chunk_repo.count_by_document.return_value = 10

        result = reporter.generate_report()

        assert result['complete'] == 1
        assert result['incomplete'] == 1
        assert len(result['issues']) == 1
        assert result['issues'][0]['file_path'] == '/test/incomplete.pdf'

    def test_handles_missing_progress_tracker(self, mock_app_state):
        """Endpoint should handle missing progress tracker gracefully"""
        from operations.completeness_reporter import CompletenessReporter

        reporter = CompletenessReporter(
            progress_tracker=None,
            vector_store=mock_app_state.core.async_vector_store
        )

        # Mock the doc_repo directly
        reporter.doc_repo = Mock()
        reporter.doc_repo.list_all.return_value = [
            {'id': 1, 'file_path': '/test/doc1.pdf'}
        ]

        # Mock chunk_repo - document has chunks
        reporter.chunk_repo = Mock()
        reporter.chunk_repo.count_by_document.return_value = 10

        result = reporter.generate_report()

        # Without tracker, can't verify progress - marked incomplete
        assert result['incomplete'] == 1

    def test_returns_empty_when_no_documents(self, mock_app_state):
        """Endpoint should handle empty document list"""
        from operations.completeness_reporter import CompletenessReporter

        reporter = CompletenessReporter(
            progress_tracker=mock_app_state.core.progress_tracker,
            vector_store=mock_app_state.core.async_vector_store
        )

        # Mock the doc_repo directly
        reporter.doc_repo = Mock()
        reporter.doc_repo.list_all.return_value = []

        # Mock chunk_repo
        reporter.chunk_repo = Mock()
        reporter.chunk_repo.count_by_document.return_value = 0

        result = reporter.generate_report()

        assert result['total_documents'] == 0
        assert result['complete'] == 0
        assert result['incomplete'] == 0
        assert result['issues'] == []


class TestCompletenessReporterIntegration:
    """Integration tests for CompletenessReporter with real analyzer"""

    def test_uses_completeness_analyzer(self):
        """Reporter should delegate to CompletenessAnalyzer"""
        from operations.completeness_reporter import CompletenessReporter
        from operations.completeness_analyzer import CompletenessAnalyzer

        mock_tracker = Mock()
        mock_store = Mock()

        reporter = CompletenessReporter(
            progress_tracker=mock_tracker,
            vector_store=mock_store
        )

        # Verify analyzer is used internally
        assert hasattr(reporter, 'analyzer') or hasattr(reporter, '_create_analyzer')
