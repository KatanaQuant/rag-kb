# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Pipeline coordinator for concurrent document processing.

Coordinates the flow of documents through extraction, chunking, embedding, and storage stages.
"""

import os
from pathlib import Path
from typing import Optional

from services.pipeline_queues import (
    PipelineQueues,
    ExtractedDocument,
    ChunkedDocument,
    EmbeddedDocument
)
from services.pipeline_workers import StageWorker, EmbedWorkerPool
from services.indexing_queue import QueueItem
from domain_models import DocumentFile

class PipelineCoordinator:
    """Coordinates concurrent pipeline processing

    Architecture:
    - ChunkWorker: Reads files, extracts text, and chunks (combined stage)
    - EmbedWorkerPool: Embeds chunks in parallel (2-4 workers)
    - StoreWorker: Stores embedded chunks in database
    """

    def __init__(self, processor, indexer, embedding_service):
        self.processor = processor
        self.indexer = indexer
        self.embedding_service = embedding_service

        # Create pipeline queues
        self.queues = PipelineQueues()

        # Get number of embed workers from environment (default: 3)
        num_embed_workers = int(os.getenv('EMBED_WORKERS', '3'))

        # Create stage workers
        self.chunk_worker = StageWorker(
            name="ChunkWorker",
            input_queue=self.queues.chunk_queue,
            output_queue=self.queues.embed_queue,
            process_fn=self._chunk_stage
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
        print(f"Starting concurrent pipeline with {len(self.embed_pool.workers)} embedding workers...")
        self.chunk_worker.start()
        self.embed_pool.start()
        self.store_worker.start()

    def stop(self):
        """Stop all pipeline workers"""
        self.chunk_worker.stop()
        self.embed_pool.stop()
        self.store_worker.stop()

    def add_file(self, item: QueueItem):
        """Add file to processing queue"""
        self.queues.chunk_queue.put(item)

    def get_stats(self) -> dict:
        """Get pipeline statistics"""
        queue_stats = self.queues.get_stats()
        return {
            'queue_sizes': queue_stats,
            'active_jobs': {
                'chunk': self.chunk_worker.get_current_item(),
                'embed': self.embed_pool.get_active_jobs(),
                'store': self.store_worker.get_current_item()
            },
            'workers_running': {
                'chunk': self.chunk_worker.is_running(),
                'embed': self.embed_pool.is_running(),
                'store': self.store_worker.is_running()
            }
        }

    # Stage processing functions

    def _chunk_stage(self, item: QueueItem) -> Optional[ChunkedDocument]:
        """Process file: extract text and chunk it"""
        try:
            print(f"[Chunk] {item.path.name}")

            # Extract and chunk in one stage
            doc_file = DocumentFile.from_path(item.path)

            # Check if already indexed (unless force=True)
            if not item.force:
                if self.embedding_service.store.is_document_indexed(str(item.path), doc_file.hash):
                    print(f"[Chunk] {item.path.name} - already indexed, skipping")
                    return None

            chunks = self.processor.process_file(doc_file)

            if not chunks:
                print(f"[Chunk] {item.path.name} - no chunks extracted")
                # Still mark as processed to avoid re-processing
                self.embedding_service.store.add_document(
                    file_path=str(doc_file.path),
                    file_hash=doc_file.hash,
                    chunks=[],
                    embeddings=[]
                )
                return None

            print(f"[Chunk] {item.path.name} - {len(chunks)} chunks created")

            return ChunkedDocument(
                priority=item.priority,
                path=item.path,
                chunks=chunks,
                hash_val=doc_file.hash,
                force=item.force
            )

        except Exception as e:
            print(f"[Chunk] Error processing {item.path}: {e}")
            return None

    def _embed_stage(self, doc: ChunkedDocument) -> Optional[EmbeddedDocument]:
        """Embed chunks"""
        try:
            print(f"[Embed] {doc.path.name} - embedding {len(doc.chunks)} chunks")

            # Use the existing embedding service
            embeddings = self.embedding_service.embed_batch(
                [chunk['content'] for chunk in doc.chunks]
            )

            print(f"[Embed] {doc.path.name} - complete")

            return EmbeddedDocument(
                priority=doc.priority,
                path=doc.path,
                chunks=doc.chunks,
                embeddings=embeddings,
                hash_val=doc.hash_val
            )

        except Exception as e:
            print(f"[Embed] Error embedding {doc.path}: {e}")
            return None

    def _store_stage(self, doc: EmbeddedDocument) -> None:
        """Store embedded chunks in database"""
        try:
            print(f"[Store] {doc.path.name} - storing {len(doc.chunks)} chunks")

            self.embedding_service.store.add_document(
                file_path=str(doc.path),
                file_hash=doc.hash_val,
                chunks=doc.chunks,
                embeddings=doc.embeddings
            )

            print(f"[Store] {doc.path.name} - complete")

        except Exception as e:
            print(f"[Store] Error storing {doc.path}: {e}")
