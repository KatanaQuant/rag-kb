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
        """Test embedding generation processes all chunks."""
        model = Mock()
        model.encode = Mock(return_value=np.array([[0.1, 0.2, 0.3]]))
        store = Mock()
        service = EmbeddingService(model, store, max_workers=2, max_pending=4)

        chunks = [
            {'content': 'chunk1'},
            {'content': 'chunk2'},
            {'content': 'chunk3'}
        ]

        embeddings = service._generate_embeddings(chunks, "test.pdf")

        assert len(embeddings) == 3
        assert model.encode.call_count == 3

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
