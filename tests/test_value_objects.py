# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for value objects."""

import pytest
from pathlib import Path
from value_objects import IndexingStats, ProcessingResult, DocumentIdentity


class TestIndexingStats:
    """Test IndexingStats value object."""

    def test_default_values(self):
        stats = IndexingStats()
        assert stats.files == 0
        assert stats.chunks == 0

    def test_custom_values(self):
        stats = IndexingStats(files=5, chunks=100)
        assert stats.files == 5
        assert stats.chunks == 100

    def test_add_file(self):
        stats = IndexingStats()
        new_stats = stats.add_file(chunks=10)
        assert new_stats.files == 1
        assert new_stats.chunks == 10
        assert stats.files == 0

    def test_add_combines_stats(self):
        stats1 = IndexingStats(files=3, chunks=30)
        stats2 = IndexingStats(files=2, chunks=20)
        combined = stats1.add(stats2)
        assert combined.files == 5
        assert combined.chunks == 50

    def test_immutable(self):
        stats = IndexingStats(files=1, chunks=10)
        with pytest.raises(Exception):
            stats.files = 2

    def test_string_representation(self):
        stats = IndexingStats(files=5, chunks=100)
        assert str(stats) == "5 files, 100 chunks"


class TestProcessingResult:
    """Test ProcessingResult value object."""

    def test_skipped_result(self):
        result = ProcessingResult.skipped()
        assert result.chunks_count == 0
        assert result.was_skipped is True
        assert result.error_message is None
        assert not result.succeeded
        assert not result.failed

    def test_success_result(self):
        result = ProcessingResult.success(chunks_count=10)
        assert result.chunks_count == 10
        assert result.was_skipped is False
        assert result.error_message is None
        assert result.succeeded
        assert not result.failed

    def test_failure_result(self):
        result = ProcessingResult.failure("test error")
        assert result.chunks_count == 0
        assert result.was_skipped is False
        assert result.error_message == "test error"
        assert not result.succeeded
        assert result.failed

    def test_immutable(self):
        result = ProcessingResult.success(10)
        with pytest.raises(Exception):
            result.chunks_count = 20


class TestDocumentIdentity:
    """Test DocumentIdentity value object."""

    def test_from_file(self):
        path = Path("/test/document.txt")
        identity = DocumentIdentity.from_file(path, "abc123")
        assert identity.path == path
        assert identity.file_hash == "abc123"
        assert identity.name == "document.txt"

    def test_string_representation(self):
        identity = DocumentIdentity(
            path=Path("/test/doc.txt"),
            file_hash="hash123",
            name="doc.txt"
        )
        assert str(identity) == "doc.txt"

    def test_immutable(self):
        identity = DocumentIdentity(
            path=Path("/test/doc.txt"),
            file_hash="hash123",
            name="doc.txt"
        )
        with pytest.raises(Exception):
            identity.name = "other.txt"
