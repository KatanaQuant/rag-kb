"""
Tests for health route module

Following TDD: These tests are written BEFORE extracting routes from main.py
Tests ensure behavior is preserved during refactoring
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock


@pytest.fixture
def mock_state():
    """Create mocked app state with async support"""
    from unittest.mock import AsyncMock

    state = Mock()
    state.core = Mock()
    state.core.vector_store = Mock()

    # Make get_vector_store_stats async (new delegation method)
    async def mock_get_stats():
        return {
            'indexed_documents': 42,
            'total_chunks': 1337
        }
    state.get_vector_store_stats = AsyncMock(side_effect=mock_get_stats)

    state.runtime = Mock()
    state.runtime.indexing_in_progress = False

    # Mock new delegation methods
    state.is_indexing_in_progress = Mock(return_value=False)

    return state


@pytest.fixture
def client(mock_state):
    """Create test client with mocked dependencies"""
    from fastapi import FastAPI
    from routes.health import router

    app = FastAPI()
    app.include_router(router)

    app.state.app_state = mock_state

    return TestClient(app)


class TestRootEndpoint:
    """Test root / endpoint"""

    def test_root_returns_api_info(self, client):
        """Root should return API info with links"""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "RAG Knowledge Base API" in data["message"]
        assert "docs" in data
        assert "health" in data
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"


class TestHealthEndpoint:
    """Test /health endpoint"""

    def test_health_returns_stats(self, client, mock_state):
        """Health endpoint should return system stats"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["indexed_documents"] == 42
        assert data["total_chunks"] == 1337
        assert "model" in data
        assert data["indexing_in_progress"] == False

        # Verify async method was called
        mock_state.get_vector_store_stats.assert_called_once()

    def test_health_includes_model_name(self, client):
        """Health should include embedding model name"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "model" in data
        assert isinstance(data["model"], str)
        assert len(data["model"]) > 0

    def test_health_shows_indexing_status(self, client, mock_state):
        """Health should show if indexing is in progress"""
        mock_state.runtime.indexing_in_progress = True
        mock_state.is_indexing_in_progress = Mock(return_value=True)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["indexing_in_progress"] == True
