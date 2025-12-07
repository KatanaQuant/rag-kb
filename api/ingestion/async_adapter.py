"""
Async adapter for VectorStore using thread pool execution.

This adapter wraps the sync VectorStore and provides an async interface
using asyncio.to_thread() for non-blocking API operations.

Architecture:
- Wraps sync VectorStore (not AsyncVectorStore)
- Uses asyncio.to_thread() for all operations
- Thread safety provided by VectorStore's internal lock
- Same interface as AsyncVectorStore for drop-in replacement

This fixes the DELETE bug caused by dual-store architecture where
AsyncVectorStore was read-only to prevent HNSW corruption.
"""

import asyncio
from typing import List, Dict, Optional


class AsyncVectorStoreAdapter:
    """Async adapter that wraps sync VectorStore for thread-safe async operations.

    Uses asyncio.to_thread() to run sync VectorStore methods in a thread pool,
    providing non-blocking behavior for API routes while maintaining thread safety.

    The underlying VectorStore uses threading.RLock for critical operations,
    ensuring no data corruption from concurrent access.
    """

    def __init__(self, vector_store):
        """Initialize adapter with sync VectorStore.

        Args:
            vector_store: Sync VectorStore instance to wrap
        """
        self._store = vector_store

    async def search(
        self,
        query_embedding: List,
        top_k: int = 5,
        threshold: float = None,
        query_text: Optional[str] = None,
        use_hybrid: bool = True
    ) -> List[Dict]:
        """Search for similar chunks using HNSW index + optional BM25.

        Runs in thread pool for non-blocking API calls.

        Args:
            query_embedding: Vector embedding of the query
            top_k: Number of results to return
            threshold: Optional similarity threshold
            query_text: Optional query text for hybrid BM25 search
            use_hybrid: Whether to use hybrid search (default True)

        Returns:
            List of matching chunks with scores and metadata
        """
        return await asyncio.to_thread(
            self._store.search,
            query_embedding,
            top_k,
            threshold,
            query_text,
            use_hybrid
        )

    async def delete_document(self, file_path: str) -> Dict:
        """Delete a document and all its chunks.

        This is the key operation that was broken in dual-store architecture.
        Now works correctly through thread pool execution with proper locking.

        Args:
            file_path: Path of the document to delete

        Returns:
            Dict with deletion result: found, document_id, chunks_deleted, document_deleted
        """
        return await asyncio.to_thread(self._store.delete_document, file_path)

    async def get_stats(self) -> Dict:
        """Get database statistics.

        Returns:
            Dict with indexed_documents and total_chunks counts
        """
        return await asyncio.to_thread(self._store.get_stats)

    async def get_document_info(self, filename: str) -> Optional[Dict]:
        """Get document information by filename.

        Args:
            filename: Name of the file to look up

        Returns:
            Dict with file_path, extraction_method, indexed_at or None if not found
        """
        return await asyncio.to_thread(self._store.get_document_info, filename)

    async def query_documents_with_chunks(self):
        """Query all documents with chunk counts.

        Returns:
            Cursor for documents joined with chunk counts
        """
        return await asyncio.to_thread(self._store.query_documents_with_chunks)

    async def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed.

        Args:
            path: File path to check
            hash_val: Hash of the file content

        Returns:
            True if document is indexed, False otherwise
        """
        return await asyncio.to_thread(self._store.is_document_indexed, path, hash_val)

    async def close(self):
        """Close adapter (no-op - store lifecycle managed by startup).

        The underlying VectorStore is not closed here because its lifecycle
        is managed by the startup manager. This adapter is just a wrapper.
        """
        pass  # Store lifecycle managed by startup manager

    async def refresh(self):
        """Refresh not needed for adapter - sync store manages its own state.

        This method exists for interface compatibility with AsyncVectorStore.
        The sync VectorStore handles HNSW index persistence via _flush_hnsw_index().
        """
        pass  # No-op for adapter
