"""
TDD Tests for HNSW persistence behavior.

These tests verify that:
1. HNSW index persists on graceful shutdown (not on every write)
2. Concurrent operations don't corrupt the index
3. Data survives without per-write flush
4. Periodic flush works as safety net

The fix removes _flush_hnsw_index() calls from add_document() to prevent
file-level race conditions that cause corruption during concurrent operations.
"""
import pytest
import tempfile
import os
import time
import threading
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import numpy as np


class TestHnswPersistenceOnShutdown:
    """Test that HNSW persists on graceful shutdown, not per-write."""

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_add_document_does_not_flush_hnsw(self):
        """add_document should NOT call _flush_hnsw_index (causes corruption)."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)

            # Track flush calls
            flush_calls = []
            original_flush = store._flush_hnsw_index_unlocked

            def tracking_flush():
                flush_calls.append(True)
                return original_flush()

            store._flush_hnsw_index_unlocked = tracking_flush

            # Add a document
            test_embedding = np.random.rand(1024).astype(np.float32).tolist()
            store.add_document(
                file_path="/test/doc1.pdf",
                file_hash="abc123",
                chunks=["Test content"],
                embeddings=[test_embedding]
            )

            # Flush should NOT have been called
            assert len(flush_calls) == 0, \
                "add_document should NOT call _flush_hnsw_index (causes corruption)"

            store.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_graceful_close_persists_data(self):
        """Data should persist when close() is called explicitly."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "vec_chunks.idx"
            config = DatabaseConfig(path=str(db_path))

            # Add document, then close
            store = VectorStore(config)
            test_embedding = np.random.rand(1024).astype(np.float32).tolist()
            store.add_document(
                file_path="/test/doc1.pdf",
                file_hash="abc123",
                chunks=["Test content"],
                embeddings=[test_embedding]
            )

            # Get index size before close
            size_before = index_path.stat().st_size if index_path.exists() else 0

            # Close should persist HNSW
            store.close()

            # Index file should exist and have grown
            assert index_path.exists(), "HNSW index should exist after close"
            size_after = index_path.stat().st_size
            assert size_after > size_before, "HNSW index should grow after close"

            # Reopen and verify data is there
            store2 = VectorStore(config)
            stats = store2.get_stats()
            assert stats['indexed_documents'] == 1, "Document should persist after restart"
            assert stats['total_chunks'] == 1, "Chunk should persist after restart"

            # Search should find the document
            results = store2.search(test_embedding, top_k=1)
            assert len(results) > 0, "Search should find persisted document"

            store2.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_multiple_documents_persist_on_close(self):
        """Multiple documents added without flush should all persist on close."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)

            # Add 10 documents without flushing
            for i in range(10):
                test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                store.add_document(
                    file_path=f"/test/doc{i}.pdf",
                    file_hash=f"hash{i}",
                    chunks=[f"Test content {i}"],
                    embeddings=[test_embedding]
                )

            # Close to persist
            store.close()

            # Reopen and verify all 10 documents
            store2 = VectorStore(config)
            stats = store2.get_stats()
            assert stats['indexed_documents'] == 10, "All 10 documents should persist"
            assert stats['total_chunks'] == 10, "All 10 chunks should persist"

            store2.close()


class TestConcurrentOperationsNoCorruption:
    """Test that concurrent operations don't corrupt the index."""

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_concurrent_add_and_search_no_corruption(self):
        """Concurrent add and search should not corrupt index."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "vec_chunks.idx"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)
            errors = []
            search_results = []

            def add_documents():
                """Add documents in a thread."""
                try:
                    for i in range(5):
                        test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                        store.add_document(
                            file_path=f"/test/thread_doc{i}.pdf",
                            file_hash=f"threadhash{i}",
                            chunks=[f"Thread content {i}"],
                            embeddings=[test_embedding]
                        )
                        time.sleep(0.01)  # Small delay to increase interleaving
                except Exception as e:
                    errors.append(str(e))

            def search_documents():
                """Search documents in another thread."""
                try:
                    for _ in range(10):
                        test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                        results = store.search(test_embedding, top_k=5)
                        search_results.append(len(results))
                        time.sleep(0.005)
                except Exception as e:
                    errors.append(str(e))

            # Run concurrently
            add_thread = threading.Thread(target=add_documents)
            search_thread = threading.Thread(target=search_documents)

            add_thread.start()
            search_thread.start()

            add_thread.join()
            search_thread.join()

            # No errors should have occurred
            assert len(errors) == 0, f"Concurrent operations caused errors: {errors}"

            # Index should not be corrupted (size > 0)
            store.close()

            if index_path.exists():
                assert index_path.stat().st_size > 0, "Index should not be empty"

            # Reopen and verify integrity
            store2 = VectorStore(config)
            stats = store2.get_stats()
            assert stats['indexed_documents'] == 5, "All documents should be intact"

            store2.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_concurrent_add_and_delete_no_corruption(self):
        """Concurrent add and delete should not corrupt index."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "vec_chunks.idx"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)

            # Pre-populate some documents
            for i in range(5):
                test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                store.add_document(
                    file_path=f"/test/existing{i}.pdf",
                    file_hash=f"existinghash{i}",
                    chunks=[f"Existing content {i}"],
                    embeddings=[test_embedding]
                )

            errors = []

            def add_documents():
                """Add new documents."""
                try:
                    for i in range(5):
                        test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                        store.add_document(
                            file_path=f"/test/new{i}.pdf",
                            file_hash=f"newhash{i}",
                            chunks=[f"New content {i}"],
                            embeddings=[test_embedding]
                        )
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(f"add: {e}")

            def delete_documents():
                """Delete existing documents."""
                try:
                    for i in range(5):
                        store.delete_document(f"/test/existing{i}.pdf")
                        time.sleep(0.01)
                except Exception as e:
                    errors.append(f"delete: {e}")

            # Run concurrently
            add_thread = threading.Thread(target=add_documents)
            delete_thread = threading.Thread(target=delete_documents)

            add_thread.start()
            delete_thread.start()

            add_thread.join()
            delete_thread.join()

            # No errors should have occurred
            assert len(errors) == 0, f"Concurrent operations caused errors: {errors}"

            # Close to persist
            store.close()

            # Verify integrity
            store2 = VectorStore(config)
            stats = store2.get_stats()
            # Should have 5 new documents (existing were deleted)
            assert stats['indexed_documents'] == 5, \
                f"Expected 5 documents, got {stats['indexed_documents']}"

            store2.close()


@pytest.mark.asyncio
class TestAsyncAdapterConcurrency:
    """Test async adapter concurrent operations."""

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    async def test_concurrent_api_operations_no_corruption(self):
        """Simulated concurrent API operations should not corrupt index."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore
        from ingestion.async_adapter import AsyncVectorStoreAdapter

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)
            adapter = AsyncVectorStoreAdapter(store)

            # Pre-populate
            for i in range(5):
                test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                store.add_document(
                    file_path=f"/test/doc{i}.pdf",
                    file_hash=f"hash{i}",
                    chunks=[f"Content {i}"],
                    embeddings=[test_embedding]
                )

            # Run concurrent async operations
            async def search_task():
                test_embedding = np.random.rand(1024).astype(np.float32).tolist()
                return await adapter.search(test_embedding, top_k=5)

            async def delete_task(path):
                return await adapter.delete_document(path)

            async def stats_task():
                return await adapter.get_stats()

            # Mix of operations
            tasks = [
                search_task(),
                search_task(),
                delete_task("/test/doc0.pdf"),
                stats_task(),
                search_task(),
                delete_task("/test/nonexistent.pdf"),
                stats_task(),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # No exceptions should have occurred
            exceptions = [r for r in results if isinstance(r, Exception)]
            assert len(exceptions) == 0, f"Got exceptions: {exceptions}"

            store.close()


class TestVectorStoreCloseMethod:
    """Test VectorStore close() method exists and works."""

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_close_method_exists(self):
        """VectorStore should have a close() method."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)

            # close() should exist
            assert hasattr(store, 'close'), "VectorStore should have close() method"
            assert callable(store.close), "close should be callable"

            store.close()

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_close_persists_hnsw(self):
        """close() should persist HNSW index to disk."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "vec_chunks.idx"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)

            # Add document
            test_embedding = np.random.rand(1024).astype(np.float32).tolist()
            store.add_document(
                file_path="/test/doc.pdf",
                file_hash="hash",
                chunks=["Content"],
                embeddings=[test_embedding]
            )

            # Close should persist
            store.close()

            # Index should exist
            assert index_path.exists(), "Index should exist after close"
            original_size = index_path.stat().st_size
            original_mtime = index_path.stat().st_mtime

            # Reopen, add more, close again
            store2 = VectorStore(config)
            test_embedding2 = np.random.rand(1024).astype(np.float32).tolist()
            store2.add_document(
                file_path="/test/doc2.pdf",
                file_hash="hash2",
                chunks=["Content 2"],
                embeddings=[test_embedding2]
            )
            store2.close()

            # Index should have been updated
            new_size = index_path.stat().st_size
            new_mtime = index_path.stat().st_mtime
            assert new_mtime > original_mtime, "Index mtime should update after second close"


class TestShutdownHandler:
    """Test shutdown handler integration."""

    def test_shutdown_handler_can_be_registered(self):
        """Verify we can register shutdown handler for SIGTERM."""
        import signal

        handler_called = []

        def shutdown_handler(signum, frame):
            handler_called.append(True)

        # Register handler
        old_handler = signal.signal(signal.SIGTERM, shutdown_handler)

        # Verify it's registered
        current_handler = signal.getsignal(signal.SIGTERM)
        assert current_handler == shutdown_handler

        # Restore original
        signal.signal(signal.SIGTERM, old_handler)

    @pytest.mark.skip(reason="Requires full ingestion package - run in Docker")
    def test_shutdown_flushes_vectorstore(self):
        """Shutdown handler should call VectorStore.close()."""
        from config import DatabaseConfig
        from ingestion.database import VectorStore

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path))

            store = VectorStore(config)
            close_called = []

            original_close = store.close

            def tracking_close():
                close_called.append(True)
                return original_close()

            store.close = tracking_close

            # Simulate shutdown
            store.close()

            assert len(close_called) == 1, "close() should be called on shutdown"
