"""
Value objects for the RAG system.

Principles:
- Immutable data structures
- Named instead of primitive types (no Primitive Obsession)
- Small, focused classes with single responsibility
"""

from dataclasses import dataclass
from typing import Optional
from pathlib import Path

@dataclass(frozen=True)
class IndexingStats:
    """Immutable statistics about indexing operations.

    Replaces dict usage like {'files': 0, 'chunks': 0} throughout codebase.
    """
    files: int = 0
    chunks: int = 0

    def add_file(self, chunks: int) -> 'IndexingStats':
        """Return new stats with file and chunks added."""
        return IndexingStats(
            files=self.files + 1,
            chunks=self.chunks + chunks
        )

    def add(self, other: 'IndexingStats') -> 'IndexingStats':
        """Combine two stats objects."""
        return IndexingStats(
            files=self.files + other.files,
            chunks=self.chunks + other.chunks
        )

    def __str__(self) -> str:
        return f"{self.files} files, {self.chunks} chunks"

@dataclass(frozen=True)
class ProcessingResult:
    """Result of processing a single document.

    Replaces tuple returns like (chunks_count, was_skipped).
    Makes code self-documenting and prevents tuple unpacking errors.
    """
    chunks_count: int
    was_skipped: bool
    error_message: Optional[str] = None

    @classmethod
    def skipped(cls) -> 'ProcessingResult':
        """Create a result for skipped file."""
        return cls(chunks_count=0, was_skipped=True)

    @classmethod
    def success(cls, chunks_count: int) -> 'ProcessingResult':
        """Create a result for successful processing."""
        return cls(chunks_count=chunks_count, was_skipped=False)

    @classmethod
    def failure(cls, error: str) -> 'ProcessingResult':
        """Create a result for failed processing."""
        return cls(chunks_count=0, was_skipped=False, error_message=error)

    @property
    def succeeded(self) -> bool:
        """Check if processing succeeded."""
        return not self.was_skipped and self.error_message is None

    @property
    def failed(self) -> bool:
        """Check if processing failed."""
        return self.error_message is not None

@dataclass(frozen=True)
class DocumentIdentity:
    """Identifies a document with all necessary information.

    Replaces passing (path, hash, name) as separate parameters.
    Ensures these values always travel together as they represent
    a single concept.
    """
    path: Path
    file_hash: str
    name: str

    @classmethod
    def from_file(cls, path: Path, file_hash: str) -> 'DocumentIdentity':
        """Create identity from file path and hash."""
        return cls(
            path=path,
            file_hash=file_hash,
            name=path.name
        )

    def __str__(self) -> str:
        return self.name
