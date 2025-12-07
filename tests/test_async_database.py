"""
Tests for async database layer

Tests verify that async database operations work correctly and don't block
the event loop during heavy operations.
"""
import pytest
import tempfile
from pathlib import Path

# pytest-asyncio is already in requirements.txt
pytestmark = pytest.mark.asyncio


class TestAsyncDatabaseConnection:
    """Test AsyncDatabaseConnection"""

    async def test_async_connection_creation(self):
        """AsyncDatabaseConnection should create async connection"""
        from ingestion.async_database import AsyncDatabaseConnection
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            conn_manager = AsyncDatabaseConnection(config)
            conn = await conn_manager.connect()

            assert conn is not None
            # Verify we can execute queries
            cursor = await conn.execute("SELECT 1")
            result = await cursor.fetchone()
            assert result[0] == 1

            await conn_manager.close()

    async def test_wal_mode_enabled(self):
        """Connection should enable WAL mode for concurrency"""
        from ingestion.async_database import AsyncDatabaseConnection
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            conn_manager = AsyncDatabaseConnection(config)
            conn = await conn_manager.connect()

            # Check WAL mode is enabled
            cursor = await conn.execute("PRAGMA journal_mode")
            result = await cursor.fetchone()
            assert result[0].lower() == 'wal'

            await conn_manager.close()


class TestAsyncSchemaManager:
    """Test AsyncSchemaManager"""

    async def test_schema_creation(self):
        """AsyncSchemaManager should create all tables"""
        from ingestion.async_database import AsyncDatabaseConnection, AsyncSchemaManager
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            conn_manager = AsyncDatabaseConnection(config)
            conn = await conn_manager.connect()

            schema_manager = AsyncSchemaManager(conn, config)
            await schema_manager.create_schema()

            # Verify tables exist
            cursor = await conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('documents', 'chunks', 'processing_progress')
            """)
            tables = await cursor.fetchall()
            table_names = [row[0] for row in tables]

            assert 'documents' in table_names
            assert 'chunks' in table_names
            assert 'processing_progress' in table_names

            await conn_manager.close()


class TestAsyncDocumentRepository:
    """Test AsyncDocumentRepository"""

    async def test_add_and_find_document(self):
        """Should add and retrieve documents asynchronously"""
        from ingestion.async_database import AsyncDatabaseConnection, AsyncSchemaManager
        from ingestion.async_repositories import AsyncDocumentRepository
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            conn_manager = AsyncDatabaseConnection(config)
            conn = await conn_manager.connect()

            # Create schema
            schema = AsyncSchemaManager(conn, config)
            await schema.create_schema()

            # Test repository
            repo = AsyncDocumentRepository(conn)
            doc_id = await repo.add("/test/file.pdf", "abc123", "docling")

            assert doc_id > 0

            # Find by hash
            doc = await repo.find_by_hash("abc123")
            assert doc is not None
            assert doc['file_path'] == "/test/file.pdf"
            assert doc['file_hash'] == "abc123"
            assert doc['extraction_method'] == "docling"

            # Find by path
            doc2 = await repo.find_by_path("/test/file.pdf")
            assert doc2 is not None
            assert doc2['id'] == doc_id

            # Count
            count = await repo.count()
            assert count == 1

            await conn_manager.close()

    async def test_document_deletion(self):
        """Should delete documents asynchronously"""
        from ingestion.async_database import AsyncDatabaseConnection, AsyncSchemaManager
        from ingestion.async_repositories import AsyncDocumentRepository
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            conn_manager = AsyncDatabaseConnection(config)
            conn = await conn_manager.connect()

            schema = AsyncSchemaManager(conn, config)
            await schema.create_schema()

            repo = AsyncDocumentRepository(conn)
            await repo.add("/test/file1.pdf", "hash1", "docling")
            await repo.add("/test/file2.pdf", "hash2", "docling")

            count_before = await repo.count()
            assert count_before == 2

            await repo.delete("/test/file1.pdf")
            await conn.commit()

            count_after = await repo.count()
            assert count_after == 1

            remaining = await repo.find_by_path("/test/file2.pdf")
            assert remaining is not None

            await conn_manager.close()


class TestAsyncVectorStore:
    """Test AsyncVectorStore integration"""

    async def test_vector_store_initialization(self):
        """AsyncVectorStore should initialize all components"""
        from ingestion.async_database import AsyncVectorStore
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = AsyncVectorStore(config)
            await store.initialize()

            # Verify components initialized
            assert store.conn is not None
            assert store.repo is not None
            assert store.repo.documents is not None
            assert store.repo.chunks is not None

            # Test get_stats
            stats = await store.get_stats()
            assert 'indexed_documents' in stats
            assert 'total_chunks' in stats
            assert stats['indexed_documents'] == 0
            assert stats['total_chunks'] == 0

            await store.close()

    async def test_concurrent_operations_dont_block(self):
        """Multiple async operations should not block each other"""
        import asyncio
        from ingestion.async_database import AsyncVectorStore
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = AsyncVectorStore(config)
            await store.initialize()

            # Run multiple get_stats() calls concurrently
            # With sync database, these would block each other
            # With async, they should run concurrently
            tasks = [store.get_stats() for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # All should succeed
            assert len(results) == 10
            for result in results:
                assert 'indexed_documents' in result

            await store.close()


class TestAsyncVectorStoreIndexRefresh:
    """Test that AsyncVectorStore auto-refreshes when index file changes"""

    async def test_refresh_detects_index_mtime_change(self):
        """AsyncVectorStore should refresh when index file mtime changes"""
        import os
        import time
        from ingestion.async_database import AsyncVectorStore
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            index_path = Path(tmpdir) / "vec_chunks.idx"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = AsyncVectorStore(config)
            await store.initialize()

            # Record initial mtime
            initial_mtime = store._index_mtime

            # Simulate sync store modifying the index file
            # (In real scenario, sync VectorStore would do this)
            index_path.write_bytes(b"dummy index data")
            time.sleep(0.01)  # Ensure mtime is different

            # Verify mtime is different now
            new_mtime = os.path.getmtime(str(index_path))
            assert new_mtime > (initial_mtime or 0), "Index file mtime should have changed"

            # Create a flag to track if refresh was called
            refresh_called = False
            original_refresh = store.refresh

            async def mock_refresh():
                nonlocal refresh_called
                refresh_called = True
                await original_refresh()

            store.refresh = mock_refresh

            # Call search - should detect mtime change and refresh
            # Note: search will fail without vectorlite, but refresh should still trigger
            try:
                await store._refresh_if_index_changed()
            except Exception:
                # May fail without vectorlite extension, but refresh should still be triggered
                pass

            assert refresh_called, "Refresh should be called when index mtime changes"

            await store.close()

    async def test_no_refresh_when_index_unchanged(self):
        """AsyncVectorStore should NOT refresh if index file unchanged"""
        from ingestion.async_database import AsyncVectorStore
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = AsyncVectorStore(config)
            await store.initialize()

            refresh_called = False
            original_refresh = store.refresh

            async def mock_refresh():
                nonlocal refresh_called
                refresh_called = True
                await original_refresh()

            store.refresh = mock_refresh

            # Call _refresh_if_index_changed without any file changes
            await store._refresh_if_index_changed()

            assert not refresh_called, "Refresh should NOT be called when index unchanged"

            await store.close()


class TestAsyncPerformance:
    """Test that async operations don't block"""

    async def test_stats_query_is_fast_during_write(self):
        """get_stats() should be fast even during write operations"""
        import asyncio
        import time
        from ingestion.async_database import AsyncVectorStore
        from ingestion.async_repositories import AsyncDocumentRepository
        from config import DatabaseConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            config = DatabaseConfig(path=str(db_path), require_vec_extension=False)

            store = AsyncVectorStore(config)
            await store.initialize()

            # Background task: Add many documents (simulates heavy indexing)
            async def background_writes():
                repo = AsyncDocumentRepository(store.conn)
                for i in range(50):
                    await repo.add(f"/test/file{i}.pdf", f"hash{i}", "docling")
                    await asyncio.sleep(0.01)  # Small delay to simulate work

            # Start background writes
            write_task = asyncio.create_task(background_writes())

            # While writing, query stats multiple times
            # This should NOT block or take 10+ seconds like sync version
            start_times = []
            durations = []

            for _ in range(10):
                await asyncio.sleep(0.05)  # Give writes time to start
                start = time.time()
                stats = await store.get_stats()
                duration = time.time() - start

                start_times.append(start)
                durations.append(duration)

                # Each query should be fast (<0.1s) even during writes
                assert duration < 0.1, f"Query took {duration}s, should be <0.1s"
                assert 'indexed_documents' in stats

            # Wait for writes to complete
            await write_task

            # Verify all documents were added
            final_stats = await store.get_stats()
            assert final_stats['indexed_documents'] == 50

            # Average query time should be very fast
            avg_duration = sum(durations) / len(durations)
            print(f"Average query time during writes: {avg_duration*1000:.2f}ms")
            assert avg_duration < 0.05, "Average query should be <50ms"

            await store.close()
