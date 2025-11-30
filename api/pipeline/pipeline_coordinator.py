# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Pipeline coordinator for concurrent document processing.

Coordinates the flow of documents through extraction, chunking, embedding, and storage stages.
"""

import os
from pathlib import Path
from typing import Optional

from pipeline.pipeline_queues import (
    PipelineQueues,
    ExtractedDocument,
    ChunkedDocument,
    EmbeddedDocument
)
from pipeline.pipeline_workers import StageWorker, EmbedWorkerPool
from pipeline.indexing_queue import QueueItem
from pipeline.progress_logger import ProgressLogger
from pipeline.skip_batcher import SkipBatcher
from domain_models import DocumentFile

class PipelineCoordinator:
    """Coordinates concurrent pipeline processing

    Architecture:
    - ChunkWorker: Reads files, extracts text, and chunks (combined stage)
    - EmbedWorkerPool: Embeds chunks in parallel (2-4 workers)
    - StoreWorker: Stores embedded chunks in database
    """

    def __init__(self, processor, indexer, embedding_service, indexing_queue=None):
        self.processor = processor
        self.indexer = indexer
        self.embedding_service = embedding_service
        self.indexing_queue = indexing_queue  # For mark_complete() callback
        self.progress_logger = ProgressLogger()
        self.skip_batcher = SkipBatcher(interval=10.0)  # Print skip summaries every 10 seconds

        # Create pipeline queues
        self.queues = PipelineQueues()

        # Get number of workers from environment
        num_chunk_workers = int(os.getenv('CHUNK_WORKERS', '1'))
        num_embed_workers = int(os.getenv('EMBEDDING_WORKERS', '2'))

        # Create stage workers
        self.chunk_pool = EmbedWorkerPool(
            num_workers=num_chunk_workers,
            input_queue=self.queues.chunk_queue,
            output_queue=self.queues.embed_queue,
            embed_fn=self._chunk_stage
        )

        self.embed_pool = EmbedWorkerPool(
            num_workers=num_embed_workers,
            input_queue=self.queues.embed_queue,
            output_queue=self.queues.store_queue,
            embed_fn=self._embed_stage
        )

        self.store_worker = StageWorker(
            name="StoreWorker",
            input_queue=self.queues.store_queue,
            output_queue=None,  # Final stage
            process_fn=self._store_stage
        )

    def start(self):
        """Start all pipeline workers"""
        print(f"Starting concurrent pipeline with {len(self.chunk_pool.workers)} chunk workers, {len(self.embed_pool.workers)} embed workers...")
        self.skip_batcher.start()
        self.chunk_pool.start()
        self.embed_pool.start()
        self.store_worker.start()

    def stop(self):
        """Stop all pipeline workers"""
        self.chunk_pool.stop()
        self.embed_pool.stop()
        self.store_worker.stop()
        self.skip_batcher.stop()  # Print final skip summary

    def add_file(self, item: QueueItem):
        """Add file to processing queue (with pre-stage skip check)

        EPUBs are handled separately - they only convert to PDF, don't chunk.
        Other files are checked if already indexed before adding to chunk_queue.
        """
        # Handle EPUB conversion outside pipeline (no chunking needed)
        if item.path.suffix.lower() == '.epub':
            self._handle_epub_conversion(item)
            return

        if self._should_skip_before_queue(item):
            self._mark_file_complete(item.path)  # Clear from queued_files tracking
            return
        self.queues.chunk_queue.put(item)

    def _should_skip_before_queue(self, item: QueueItem) -> bool:
        """Pre-stage skip check - filter out already-indexed files

        This runs BEFORE adding to chunk_queue, keeping queue size minimal.
        Only files that actually need processing enter the queue.
        """
        if item.force:
            return False  # Force reprocessing requested

        try:
            doc_file = DocumentFile.from_path(item.path)
            if self.embedding_service.store.is_document_indexed(str(item.path), doc_file.hash):
                self.skip_batcher.record_skip(item.path.name, "already indexed")
                return True
        except Exception:
            # If we can't check, let it through to chunk_stage for proper error handling
            pass

        return False

    def get_stats(self) -> dict:
        """Get pipeline statistics"""
        queue_stats = self.queues.get_stats()
        return {
            'queue_sizes': queue_stats,
            'active_jobs': {
                'chunk': self.chunk_pool.get_active_jobs(),
                'embed': self.embed_pool.get_active_jobs(),
                'store': self.store_worker.get_current_item()
            },
            'workers_running': {
                'chunk': self.chunk_pool.is_running(),
                'embed': self.embed_pool.is_running(),
                'store': self.store_worker.is_running()
            }
        }

    # Stage processing functions

    def _chunk_stage(self, item: QueueItem) -> Optional[ChunkedDocument]:
        """Process file: extract text and chunk it

        Note: EPUBs are handled separately in _handle_epub_conversion()
        and never reach this method.
        """
        try:
            doc_file = DocumentFile.from_path(item.path)

            if self._should_skip_indexed_file(item, doc_file):
                self._mark_file_complete(item.path)  # Mark complete even if skipped
                return None

            self._log_processing_start("Chunk", item.path.name)

            chunks = self.processor.process_file(doc_file, force=item.force)

            if not chunks:
                self._mark_file_complete(item.path)  # Mark complete even if no chunks
                print(f"[Chunk] {item.path.name} - no chunks extracted")
                self.progress_logger.log_complete("Chunk", item.path.name, 0)
                return None

            self.progress_logger.log_complete("Chunk", item.path.name, len(chunks))
            return self._create_chunked_document(item, doc_file, chunks)

        except Exception as e:
            print(f"[Chunk] Error processing {item.path}: {e}")
            self._mark_file_complete(item.path)  # Mark complete on error
            return None

    def _handle_epub_conversion(self, item: QueueItem):
        """Handle EPUB conversion outside the chunking pipeline

        EPUBs only convert to PDF - they don't need chunking/embedding.
        The converted PDF will be picked up by file watcher and indexed separately.
        """
        try:
            print(f"[Convert] {item.path.name}")
            doc_file = DocumentFile.from_path(item.path)

            # Just do the conversion (returns empty chunks)
            self.processor.process_file(doc_file, force=item.force)

            print(f"[Convert] {item.path.name} - conversion complete, PDF queued for indexing")
            self._mark_file_complete(item.path)
        except Exception as e:
            print(f"[Convert] Error converting {item.path}: {e}")
            self._mark_file_complete(item.path)

    def _mark_file_complete(self, path: Path):
        """Mark file as complete in indexing queue"""
        if self.indexing_queue:
            self.indexing_queue.mark_complete(path)

    def _should_skip_indexed_file(self, item: QueueItem, doc_file) -> bool:
        """Check if file should be skipped (already indexed)"""
        if item.force:
            return False
        if self.embedding_service.store.is_document_indexed(str(item.path), doc_file.hash):
            self.skip_batcher.record_skip(item.path.name, "already indexed")
            return True
        return False

    def _log_processing_start(self, stage: str, filename: str):
        """Log processing start with heartbeat"""
        self.progress_logger.log_start(stage, filename)
        self.progress_logger.start_heartbeat(stage, filename, interval=60)

    def _create_chunked_document(self, item: QueueItem, doc_file, chunks) -> ChunkedDocument:
        """Create ChunkedDocument from processing results"""
        return ChunkedDocument(
            priority=item.priority,
            path=item.path,
            chunks=chunks,
            hash_val=doc_file.hash,
            force=item.force
        )

    def _embed_stage(self, doc: ChunkedDocument) -> Optional[EmbeddedDocument]:
        """Embed chunks"""
        try:
            self.progress_logger.log_start("Embed", doc.path.name)

            # Use the existing embedding service
            embeddings = self.embedding_service.embed_batch(
                texts=[chunk['content'] for chunk in doc.chunks],
                document_name=doc.path.name,
                progress_logger=self.progress_logger
            )

            self.progress_logger.log_complete("Embed", doc.path.name, len(doc.chunks))

            return EmbeddedDocument(
                priority=doc.priority,
                path=doc.path,
                chunks=doc.chunks,
                embeddings=embeddings,
                hash_val=doc.hash_val
            )

        except Exception as e:
            print(f"[Embed] Error embedding {doc.path}: {e}")
            self._mark_file_complete(doc.path)  # Mark complete on error
            return None

    def _store_stage(self, doc: EmbeddedDocument) -> None:
        """Store embedded chunks in database"""
        try:
            self.progress_logger.log_start("Store", doc.path.name)

            self.embedding_service.store.add_document(
                file_path=str(doc.path),
                file_hash=doc.hash_val,
                chunks=doc.chunks,
                embeddings=doc.embeddings
            )

            self.progress_logger.log_complete("Store", doc.path.name, len(doc.chunks))
            self._mark_file_complete(doc.path)

        except Exception as e:
            print(f"[Store] Error storing {doc.path}: {e}")
            self._mark_file_complete(doc.path)  # Mark complete on error too
