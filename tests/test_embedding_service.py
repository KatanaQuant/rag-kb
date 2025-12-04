# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for EmbeddingService."""

import time
import numpy as np
from unittest.mock import Mock, MagicMock
from pipeline.embedding_service import EmbeddingService
from value_objects import DocumentIdentity
from pathlib import Path


class TestEmbeddingService:
    """Test EmbeddingService."""

    def test_initialization(self):
        """Test service initialization."""
        model = Mock()
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        assert service.model is model
        assert service.store is store
        assert service.max_pending == 4
        assert len(service.pending) == 0
        assert len(service.failed) == 0

    def test_queue_embedding(self):
        """Test queuing an embedding task."""
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2, 0.3]]))
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        identity = DocumentIdentity(
            path=Path("/test/doc.pdf"),
            file_hash="abc123",
            name="doc.pdf"
        )
        chunks = [{'content': 'test chunk'}]

        future = service.queue_embedding(identity, chunks)

        assert future is not None
        assert len(service.pending) == 1

    def test_wait_for_all_completes(self):
        """Test waiting for all embeddings to complete."""
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2, 0.3]]))
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        identity = DocumentIdentity(
            path=Path("/test/doc.pdf"),
            file_hash="abc123",
            name="doc.pdf"
        )
        chunks = [{'content': 'test chunk'}]

        service.queue_embedding(identity, chunks)
        service.wait_for_all()

        assert len(service.pending) == 0
        store.add_document.assert_called_once()

    def test_throttling_when_max_pending_reached(self):
        """Test throttling prevents too many pending tasks."""
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2, 0.3]]))
        store = Mock()

        # Set very low max_pending for testing
        service = EmbeddingService(model, store, max_workers=2, max_pending=1)

        identity1 = DocumentIdentity(Path("/test/doc1.pdf"), "hash1", "doc1.pdf")
        identity2 = DocumentIdentity(Path("/test/doc2.pdf"), "hash2", "doc2.pdf")
        chunks = [{'content': 'test'}]

        # First should queue immediately
        service.queue_embedding(identity1, chunks)

        # Second should wait until first completes
        service.queue_embedding(identity2, chunks)

        # Should have processed both
        service.wait_for_all()
        assert store.add_document.call_count == 2

    def test_embedding_failure_recorded(self):
        """Test embedding failures are recorded."""
        model = Mock()
        model.encode = Mock(side_effect=Exception("Encoding failed"))
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        identity = DocumentIdentity(Path("/test/doc.pdf"), "hash1", "doc.pdf")
        chunks = [{'content': 'test'}]

        service.queue_embedding(identity, chunks)
        service.wait_for_all()

        assert len(service.failed) == 1
        assert service.failed[0]['name'] == 'doc.pdf'
        assert 'Encoding failed' in service.failed[0]['error']

    def test_cleanup_completed_removes_done_futures(self):
        """Test cleanup removes completed futures."""
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2, 0.3]]))
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        identity = DocumentIdentity(Path("/test/doc.pdf"), "hash1", "doc.pdf")
        chunks = [{'content': 'test'}]

        service.queue_embedding(identity, chunks)
        time.sleep(0.1)  # Let it complete

        service._cleanup_completed()

        assert len(service.pending) == 0

    def test_generate_embeddings_processes_all_chunks(self):
        """Test embedding generation processes all chunks using batch encoding."""
        model = Mock()
        # Batch encoding returns all embeddings in one call
        model.encode = Mock(return_value=np.array([
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9]
        ]))
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        chunks = [
            {'content': 'chunk1'},
            {'content': 'chunk2'},
            {'content': 'chunk3'}
        ]

        embeddings = service._generate_embeddings(chunks, "test.pdf")

        assert len(embeddings) == 3
        # With batch encoding, model.encode is called once for all chunks (batch_size=32 default)
        assert model.encode.call_count == 1

    def test_store_document_calls_vector_store(self):
        """Test document storage calls vector store."""
        model = Mock()
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        identity = DocumentIdentity(Path("/test/doc.pdf"), "hash1", "doc.pdf")
        chunks = [{'content': 'test'}]
        embeddings = [[0.1, 0.2, 0.3]]

        service._store_document(identity, chunks, embeddings)

        store.add_document.assert_called_once_with(
            file_path="/test/doc.pdf",
            file_hash="hash1",
            chunks=chunks,
            embeddings=embeddings
        )


class TestBatchEncoder:
    """Test BatchEncoder - extracts batch encoding responsibility from EmbeddingService.

    Single Responsibility Principle: Only handles batch encoding logic.
    Following Kent Beck TDD: Red-Green-Refactor cycle.
    """

    def test_initialization_with_model(self):
        """Test BatchEncoder initializes with model dependency."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        encoder = BatchEncoder(model)
        assert encoder.model is model

    def test_initialization_with_default_batch_size(self):
        """Test BatchEncoder has sensible default batch size."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        encoder = BatchEncoder(model)
        assert encoder.batch_size == 32  # Optimal for CPU

    def test_initialization_with_custom_batch_size(self):
        """Test BatchEncoder accepts custom batch size."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        encoder = BatchEncoder(model, batch_size=64)
        assert encoder.batch_size == 64

    def test_encode_single_text(self):
        """Test encoding a single text."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2, 0.3]]))
        encoder = BatchEncoder(model)

        result = encoder.encode(["hello world"])

        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
        model.encode.assert_called_once()

    def test_encode_multiple_texts_in_single_batch(self):
        """Test encoding multiple texts calls model.encode once when under batch_size."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        model.encode = Mock(return_value=np.array([
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9]
        ]))
        encoder = BatchEncoder(model, batch_size=32)

        texts = ["text1", "text2", "text3"]
        result = encoder.encode(texts)

        assert len(result) == 3
        # Key assertion: model.encode called ONCE with all texts (batch encoding)
        assert model.encode.call_count == 1
        call_args = model.encode.call_args
        assert call_args[0][0] == texts  # First positional arg is the texts list

    def test_encode_batches_large_input(self):
        """Test encoding splits large input into batches."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        # Return different embeddings for each batch
        model.encode = Mock(side_effect=[
            np.array([[0.1] * 3] * 2),  # First batch of 2
            np.array([[0.2] * 3] * 2),  # Second batch of 2
            np.array([[0.3] * 3] * 1),  # Third batch of 1
        ])
        encoder = BatchEncoder(model, batch_size=2)

        texts = ["t1", "t2", "t3", "t4", "t5"]  # 5 texts, batch_size=2 -> 3 batches
        result = encoder.encode(texts)

        assert len(result) == 5
        # 5 texts / 2 batch_size = 3 batches (2, 2, 1)
        assert model.encode.call_count == 3

    def test_encode_empty_list_returns_empty(self):
        """Test encoding empty list returns empty list without calling model."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        encoder = BatchEncoder(model)

        result = encoder.encode([])

        assert result == []
        model.encode.assert_not_called()

    def test_encode_preserves_order(self):
        """Test encoding preserves order of inputs."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        # Each batch returns unique embeddings
        model.encode = Mock(side_effect=[
            np.array([[1.0, 0.0], [2.0, 0.0]]),
            np.array([[3.0, 0.0], [4.0, 0.0]]),
        ])
        encoder = BatchEncoder(model, batch_size=2)

        texts = ["first", "second", "third", "fourth"]
        result = encoder.encode(texts)

        assert result[0] == [1.0, 0.0]
        assert result[1] == [2.0, 0.0]
        assert result[2] == [3.0, 0.0]
        assert result[3] == [4.0, 0.0]

    def test_encode_with_progress_callback(self):
        """Test encoding calls progress callback for each batch."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2]]))
        encoder = BatchEncoder(model, batch_size=2)

        progress_calls = []
        def on_progress(batch_num, total_batches, items_done, total_items):
            progress_calls.append((batch_num, total_batches, items_done, total_items))

        texts = ["t1", "t2", "t3"]  # 3 texts, batch_size=2 -> 2 batches
        encoder.encode(texts, on_progress=on_progress)

        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, 2, 3)  # After first batch: 2 done
        assert progress_calls[1] == (2, 2, 3, 3)  # After second batch: 3 done

    def test_timing_disabled_by_default(self):
        """Test timing is disabled by default."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        encoder = BatchEncoder(model)
        assert encoder.enable_timing is False

    def test_timing_can_be_enabled(self):
        """Test timing can be enabled via constructor."""
        from pipeline.batch_encoder import BatchEncoder
        model = Mock()
        encoder = BatchEncoder(model, enable_timing=True)
        assert encoder.enable_timing is True
