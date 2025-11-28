# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Embedding service for managing concurrent embedding operations."""

import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Dict, Any
from pathlib import Path

from pipeline.batch_encoder import BatchEncoder


class EmbeddingService:
    """Manages concurrent embedding operations with throttling."""

    def __init__(self, model, vector_store, max_workers: int, max_pending: int, processor=None, batch_size: int = 32):
        self.model = model
        self.store = vector_store
        self.processor = processor
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.max_pending = max_pending
        self.pending: List[Future] = []
        self.failed: List[Dict[str, Any]] = []
        self.batch_encoder = BatchEncoder(model, batch_size=batch_size)

    def queue_embedding(self, identity, chunks: List) -> Future:
        """Queue embedding task for concurrent execution."""
        self._cleanup_completed()
        self._throttle_if_needed()
        print(f"Embedding queued: {identity.name} - {len(chunks)} chunks")
        future = self.executor.submit(self._embed_and_store, identity, chunks)
        self.pending.append(future)
        return future

    def wait_for_all(self):
        """Wait for all pending embeddings to complete."""
        self._cleanup_completed()
        if not self.pending:
            return
        total = len(self.pending)
        print(f"Waiting for {total} pending embedding tasks...")
        completed = 0
        failed = 0
        for future in self.pending:
            try:
                future.result()
                completed += 1
            except Exception:
                failed += 1
        self.pending.clear()
        self._report_completion(completed, failed)

    def _cleanup_completed(self):
        """Remove completed futures from pending list."""
        self.pending = [f for f in self.pending if not f.done()]

    def _throttle_if_needed(self):
        """Throttle if too many embeddings pending."""
        if len(self.pending) >= self.max_pending:
            print(f"Throttling: {len(self.pending)} embeddings pending (max: {self.max_pending})")
            while len(self.pending) >= self.max_pending:
                self.pending = [f for f in self.pending if not f.done()]
                time.sleep(0.5)
            print(f"Throttling released: {len(self.pending)} pending")

    def _embed_and_store(self, identity, chunks):
        """Embed and store chunks with timing and error handling."""
        start_time = time.time()
        try:
            print(f"Embedding started: {identity.name} - {len(chunks)} chunks")
            embeddings = self._generate_embeddings(chunks, identity.name)
            elapsed = time.time() - start_time
            print(f"Embedding complete: {identity.name} - {len(chunks)} chunks embedded in {elapsed:.1f}s")
            store_start = time.time()
            self._store_document(identity, chunks, embeddings)
            store_elapsed = time.time() - store_start
            total_elapsed = time.time() - start_time
            print(f"Indexed {identity.name}: {len(chunks)} chunks stored (embed: {elapsed:.1f}s, store: {store_elapsed:.1f}s, total: {total_elapsed:.1f}s)")
        except Exception as e:
            self._handle_failure(identity, chunks, e, start_time)
            raise

    def is_indexed(self, path: str, file_hash: str) -> bool:
        """Check if document is already indexed.

        Delegation method to avoid Law of Demeter violation.
        """
        return self.store.is_document_indexed(path, file_hash)

    def add_empty_document(self, file_path: str, file_hash: str):
        """Add document with no chunks to mark as processed.

        Delegation method to avoid Law of Demeter violation.
        """
        self.store.add_document(
            file_path=file_path,
            file_hash=file_hash,
            chunks=[],
            embeddings=[]
        )

    def embed_batch(self, texts: List[str], document_name: str = None, progress_logger=None) -> List:
        """Embed a batch of text chunks using batch encoding.

        Public method for pipeline to generate embeddings.
        Uses BatchEncoder for efficient batch processing (10-50x faster).

        Args:
            texts: List of text strings to embed
            document_name: Optional document name for progress logging
            progress_logger: Optional ProgressLogger instance

        Returns:
            List of embeddings (each is a list of floats)
        """
        def on_progress(batch_num, total_batches, items_done, total_items):
            if progress_logger and document_name:
                progress_logger.log_progress("Embed", document_name, items_done, total_items)

        return self.batch_encoder.encode(texts, on_progress=on_progress)

    def _generate_embeddings(self, chunks: List, name: str) -> List:
        """Generate embeddings using batch encoding.

        Uses BatchEncoder for efficient batch processing instead of
        one-at-a-time encoding (10-50x faster for large documents).
        """
        texts = [c['content'] for c in chunks]

        def on_progress(batch_num, total_batches, items_done, total_items):
            file_indicator = f" ({name})" if name else ""
            print(f"  Encoding batch {batch_num}/{total_batches} ({items_done}/{total_items} chunks){file_indicator}")

        return self.batch_encoder.encode(texts, on_progress=on_progress)

    def _store_document(self, identity, chunks, embeddings):
        """Store document in vector store."""
        self.store.add_document(
            file_path=str(identity.path),
            file_hash=identity.file_hash,
            chunks=chunks,
            embeddings=embeddings
        )

    def _handle_failure(self, identity, chunks, error, start_time):
        """Record and report embedding failure."""
        elapsed = time.time() - start_time
        error_msg = f"Embedding failed for {identity.name} after {elapsed:.1f}s: {type(error).__name__}: {str(error)}"
        print(f"ERROR: {error_msg}")
        self.failed.append({
            'path': str(identity.path),
            'name': identity.name,
            'chunks': len(chunks),
            'error': str(error),
            'elapsed': elapsed
        })
        # Mark as failed in progress tracker if available
        if self.processor and hasattr(self.processor, 'tracker') and self.processor.tracker:
            self.processor.tracker.mark_failed(str(identity.path), str(error))

    def _report_completion(self, completed: int, failed: int):
        """Report completion statistics."""
        if failed > 0:
            print(f"Embeddings complete: {completed} succeeded, {failed} failed")
            if self.failed:
                print(f"\nFailed embeddings:")
                for failure in self.failed[:5]:
                    print(f"  - {failure['name']}: {failure['error'][:100]}")
                if len(self.failed) > 5:
                    print(f"  ... and {len(self.failed) - 5} more")
        else:
            print(f"All {completed} pending embeddings complete")
