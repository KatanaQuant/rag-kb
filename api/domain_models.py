"""Domain models for ingestion pipeline"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class ChunkData:
    """Represents a single chunk of text with metadata"""
    content: str
    page: Optional[int] = None
    token_count: Optional[int] = None

    def is_valid(self, min_size: int = 50) -> bool:
        """Check if chunk meets minimum size requirement"""
        return len(self.content.strip()) >= min_size

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage"""
        return {
            'content': self.content,
            'page': self.page,
            'token_count': self.token_count
        }

@dataclass
class DocumentFile:
    """Represents a document file with its hash

    Following Sandi Metz 'Tell, Don't Ask': This class knows how to create
    itself from a path, encapsulating the hash calculation logic.
    """
    path: Path
    hash: str

    @classmethod
    def from_path(cls, path: Path) -> 'DocumentFile':
        """Factory method to create DocumentFile from path

        Following Sandi Metz principles:
        - Feature Envy Fix: DocumentFile knows how to hash itself
        - Single Responsibility: Encapsulates document file creation
        - Dependency Injection: Can be overridden for testing

        Args:
            path: Path to document file

        Returns:
            DocumentFile with computed hash
        """
        from ingestion.helpers import FileHasher
        file_hash = FileHasher.hash_file(path)
        return cls(path=path, hash=file_hash)

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()

    @property
    def name(self) -> str:
        return self.path.name

    def exists(self) -> bool:
        return self.path.exists()

@dataclass
class ExtractionResult:
    """Result of text extraction from document"""
    pages: list[tuple[str, Optional[int]]]  # List of (text, page_num) tuples
    method: str  # 'docling', 'pypdf', 'markdown', etc.
    success: bool = True
    error: Optional[str] = None

    @property
    def page_count(self) -> int:
        """Number of pages extracted"""
        return len(self.pages)

    @property
    def total_chars(self) -> int:
        """Total characters extracted"""
        return sum(len(text) for text, _ in self.pages)
