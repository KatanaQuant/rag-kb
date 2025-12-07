"""
Tests for unified VectorStore architecture using AsyncVectorStoreAdapter.

This tests the adapter pattern that wraps the sync VectorStore for async use,
eliminating the dual-store architecture that caused DELETE operation issues.

Problem solved: AsyncVectorStore was read-only to prevent HNSW corruption,
which broke DELETE operations from the API. The adapter pattern uses
asyncio.to_thread() to run sync VectorStore operations in a thread pool,
maintaining thread safety while providing async interface.
"""
import pytest
import tempfile
import asyncio
import sys
import importlib.util
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import numpy as np

# Helper to import async_adapter directly without triggering full ingestion package
def load_async_adapter():
    """Load async_adapter module directly to avoid heavy dependencies."""
    # Try host path first, fall back to Docker path
    adapter_path = Path(__file__).parent.parent / "api" / "ingestion" / "async_adapter.py"
    if not adapter_path.exists():
        adapter_path = Path(__file__).parent.parent / "ingestion" / "async_adapter.py"
    spec = importlib.util.spec_from_file_location("async_adapter", adapter_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AsyncVectorStoreAdapter

# Note: pytestmark = pytest.mark.asyncio not used at module level
# Individual async test classes/methods are decorated separately


@pytest.mark.asyncio
class TestAsyncVectorStoreAdapter:
    """Test AsyncVectorStoreAdapter wraps sync VectorStore correctly."""

    async def test_adapter_wraps_sync_store(self):
        """Adapter should wrap sync VectorStore and expose same interface."""
        AsyncVectorStoreAdapter = load_async_adapter()

        # Create mock sync store
        mock_store = Mock()
        mock_store.get_stats.return_value = {
            'indexed_documents': 10,
            'total_chunks': 100
        }

        adapter = AsyncVectorStoreAdapter(mock_store)

        # Call async method
        stats = await adapter.get_stats()

        # Verify delegation to sync store
        assert stats['indexed_documents'] == 10
        assert stats['total_chunks'] == 100
        mock_store.get_stats.assert_called_once()

    async def test_adapter_delete_works(self):
        """DELETE via async adapter should work (this is the key bug fix)."""
        AsyncVectorStoreAdapter = load_async_adapter()

        # Create mock sync store with delete_document method
        mock_store = Mock()
        mock_store.delete_document.return_value = {
            'found': True,
            'document_id': 1,
            'chunks_deleted': 5,
            'document_deleted': True
        }

        adapter = AsyncVectorStoreAdapter(mock_store)

        # Call async delete
        result = await adapter.delete_document("/test/document.pdf")

        # Verify deletion succeeded
        assert result['found'] is True
        assert result['document_deleted'] is True
        assert result['chunks_deleted'] == 5
        mock_store.delete_document.assert_called_once_with("/test/document.pdf")

    async def test_adapter_delete_returns_not_found(self):
        """DELETE should return not found for non-existent documents."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        mock_store.delete_document.return_value = {
            'found': False,
            'chunks_deleted': 0,
            'document_deleted': False
        }

        adapter = AsyncVectorStoreAdapter(mock_store)

        result = await adapter.delete_document("/test/nonexistent.pdf")

        assert result['found'] is False
        assert result['document_deleted'] is False

    async def test_adapter_search_works(self):
        """Search via async adapter should return results."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        mock_store.search.return_value = [
            {'content': 'Test chunk 1', 'score': 0.95, 'file_path': '/test/doc1.pdf'},
            {'content': 'Test chunk 2', 'score': 0.90, 'file_path': '/test/doc2.pdf'},
        ]

        adapter = AsyncVectorStoreAdapter(mock_store)

        # Create test embedding
        test_embedding = [0.1] * 1024

        results = await adapter.search(
            query_embedding=test_embedding,
            top_k=5,
            query_text="test query"
        )

        assert len(results) == 2
        assert results[0]['score'] == 0.95
        mock_store.search.assert_called_once()

    async def test_adapter_uses_thread_pool(self):
        """Adapter should use asyncio.to_thread for non-blocking operations."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        mock_store.get_stats.return_value = {'indexed_documents': 5, 'total_chunks': 50}

        adapter = AsyncVectorStoreAdapter(mock_store)

        # Run multiple concurrent calls - should not block each other
        async def get_stats_task():
            return await adapter.get_stats()

        # Run 10 concurrent calls
        tasks = [get_stats_task() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        for result in results:
            assert result['indexed_documents'] == 5

    async def test_adapter_get_document_info(self):
        """get_document_info should work through adapter."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        mock_store.get_document_info.return_value = {
            'file_path': '/test/document.pdf',
            'extraction_method': 'docling',
            'indexed_at': '2024-01-01 12:00:00'
        }

        adapter = AsyncVectorStoreAdapter(mock_store)

        info = await adapter.get_document_info("document.pdf")

        assert info['file_path'] == '/test/document.pdf'
        assert info['extraction_method'] == 'docling'

    async def test_adapter_query_documents_with_chunks(self):
        """query_documents_with_chunks should work through adapter."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            ('/test/doc1.pdf', '2024-01-01', 10),
            ('/test/doc2.pdf', '2024-01-02', 20),
        ]
        mock_store.query_documents_with_chunks.return_value = mock_cursor

        adapter = AsyncVectorStoreAdapter(mock_store)

        cursor = await adapter.query_documents_with_chunks()
        results = cursor.fetchall()

        assert len(results) == 2
        assert results[0][2] == 10  # chunk count


class TestVectorStoreThreadSafety:
    """Test thread safety additions to VectorStore.

    These tests verify that VectorStore has proper locking for thread-safe
    concurrent access from the async adapter's thread pool.

    Note: These tests are skipped by default because they require the full
    ingestion package with all dependencies. They can be run in the Docker
    environment where all dependencies are installed.
    """

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_vector_store_has_lock(self):
        """VectorStore should have a threading lock."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = VectorStore(config)

            # Check lock exists
            assert hasattr(store, '_lock')
            import threading
            assert isinstance(store._lock, type(threading.RLock()))

            store.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_search_is_thread_safe(self):
        """search() should be protected by lock."""
        import threading
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = VectorStore(config)

            # Track lock acquisitions
            lock_acquired = []
            original_enter = store._lock.__enter__

            def tracking_enter():
                lock_acquired.append(True)
                return original_enter()

            store._lock.__enter__ = tracking_enter

            # Mock repo.search to avoid actual search
            store.repo.search = Mock(return_value=[])

            # Call search
            try:
                store.search([0.1] * 1024, top_k=5)
            except Exception:
                # May fail without vectorlite extension, but lock should still be acquired
                pass

            # Verify lock was acquired
            assert len(lock_acquired) > 0, "Lock should be acquired during search"

            store.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_delete_document_is_thread_safe(self):
        """delete_document() should be protected by lock."""
        import threading
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = VectorStore(config)

            # Track lock acquisitions
            lock_acquired = []
            original_enter = store._lock.__enter__

            def tracking_enter():
                lock_acquired.append(True)
                return original_enter()

            store._lock.__enter__ = tracking_enter

            # Call delete
            store.delete_document("/test/nonexistent.pdf")

            # Verify lock was acquired
            assert len(lock_acquired) > 0, "Lock should be acquired during delete"

            store.close()


@pytest.mark.asyncio
class TestAdapterIntegration:
    """Integration tests for adapter with real VectorStore.

    Note: These tests are skipped by default because they require the full
    ingestion package with all dependencies. They can be run in the Docker
    environment where all dependencies are installed.
    """

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    async def test_adapter_with_real_store_stats(self):
        """Adapter should work with real VectorStore for get_stats."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore
        from ingestion.async_adapter import AsyncVectorStoreAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = VectorStore(config)
            adapter = AsyncVectorStoreAdapter(store)

            stats = await adapter.get_stats()

            assert 'indexed_documents' in stats
            assert 'total_chunks' in stats
            assert stats['indexed_documents'] == 0

            store.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    async def test_adapter_with_real_store_delete(self):
        """Adapter should work with real VectorStore for delete."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore
        from ingestion.async_adapter import AsyncVectorStoreAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = VectorStore(config)
            adapter = AsyncVectorStoreAdapter(store)

            # Delete non-existent document
            result = await adapter.delete_document("/test/nonexistent.pdf")

            assert result['found'] is False
            assert result['document_deleted'] is False

            store.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    async def test_concurrent_delete_operations(self):
        """Multiple concurrent deletes should not cause corruption."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore
        from ingestion.async_adapter import AsyncVectorStoreAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = VectorStore(config)
            adapter = AsyncVectorStoreAdapter(store)

            # Run concurrent delete operations
            async def delete_task(path):
                return await adapter.delete_document(path)

            tasks = [delete_task(f"/test/doc{i}.pdf") for i in range(10)]
            results = await asyncio.gather(*tasks)

            # All should complete without error
            assert len(results) == 10
            for result in results:
                assert result['found'] is False  # None exist

            store.close()


class TestAppStateLazyAdapter:
    """Test that AppState lazily creates the adapter."""

    def test_core_services_creates_adapter_lazily(self):
        """CoreServices should create adapter lazily when async_vector_store accessed."""
        # Import directly to avoid heavy dependencies
        # Try host path first, fall back to Docker path
        app_state_path = Path(__file__).parent.parent / "api" / "app_state.py"
        if not app_state_path.exists():
            app_state_path = Path(__file__).parent.parent / "app_state.py"
        spec = importlib.util.spec_from_file_location("app_state", app_state_path)

        # Need to mock value_objects import
        import sys
        mock_value_objects = type(sys)('value_objects')
        mock_value_objects.IndexingStats = Mock
        sys.modules['value_objects'] = mock_value_objects

        # Also mock the ingestion.async_adapter import
        AsyncVectorStoreAdapter = load_async_adapter()

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        CoreServices = module.CoreServices

        core = CoreServices()

        # Initially no adapter
        assert core._async_adapter is None

        # Without vector_store, should return None
        assert core.async_vector_store is None

        # Set up mock vector store
        mock_store = Mock()
        core.vector_store = mock_store

        # Now accessing async_vector_store should create adapter
        # But we need to mock the import
        with patch.dict('sys.modules', {'ingestion.async_adapter': Mock(AsyncVectorStoreAdapter=AsyncVectorStoreAdapter)}):
            adapter = core.async_vector_store

        assert adapter is not None
        # Accessing again should return same instance
        adapter2 = core.async_vector_store
        assert adapter is adapter2

    def test_core_services_setter_works(self):
        """Setting async_vector_store directly should work."""
        # Try host path first, fall back to Docker path
        app_state_path = Path(__file__).parent.parent / "api" / "app_state.py"
        if not app_state_path.exists():
            app_state_path = Path(__file__).parent.parent / "app_state.py"
        spec = importlib.util.spec_from_file_location("app_state", app_state_path)

        import sys
        mock_value_objects = type(sys)('value_objects')
        mock_value_objects.IndexingStats = Mock
        sys.modules['value_objects'] = mock_value_objects

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        CoreServices = module.CoreServices

        core = CoreServices()

        # Set adapter directly
        mock_adapter = Mock()
        core.async_vector_store = mock_adapter

        # Should return the set value
        assert core.async_vector_store is mock_adapter


@pytest.mark.asyncio
class TestAdapterInterface:
    """Test that adapter has the same interface as AsyncVectorStore."""

    async def test_adapter_has_required_methods(self):
        """Adapter should have all methods that AsyncVectorStore has."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        adapter = AsyncVectorStoreAdapter(mock_store)

        # Check all required async methods exist
        assert hasattr(adapter, 'search')
        assert hasattr(adapter, 'delete_document')
        assert hasattr(adapter, 'get_stats')
        assert hasattr(adapter, 'get_document_info')
        assert hasattr(adapter, 'query_documents_with_chunks')

        # All should be coroutine functions
        assert asyncio.iscoroutinefunction(adapter.search)
        assert asyncio.iscoroutinefunction(adapter.delete_document)
        assert asyncio.iscoroutinefunction(adapter.get_stats)
        assert asyncio.iscoroutinefunction(adapter.get_document_info)
        assert asyncio.iscoroutinefunction(adapter.query_documents_with_chunks)

    async def test_adapter_close_is_noop(self):
        """Adapter close should be a no-op (store lifecycle managed elsewhere)."""
        AsyncVectorStoreAdapter = load_async_adapter()

        mock_store = Mock()
        adapter = AsyncVectorStoreAdapter(mock_store)

        # Close should not raise and should not close the underlying store
        await adapter.close()

        # Store's close should NOT be called - lifecycle managed by startup
        mock_store.close.assert_not_called()
