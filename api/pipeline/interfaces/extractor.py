"""Extractor interface for document text extraction.

Defines the contract for all document extractors (PDF, DOCX, code, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Set

from domain_models import ExtractionResult


class ExtractorInterface(ABC):
    """Interface for document text extractors.

    Contract (Liskov Substitution):
        - extract() must return ExtractionResult
        - Must handle file not found gracefully (return error result)
        - Must not raise exceptions for supported file types
    """

    SUPPORTED_EXTENSIONS: ClassVar[Set[str]] = set()

    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult:
        """Extract text content from a document.

        Args:
            path: Path to the document file

        Returns:
            ExtractionResult with pages, method, and success status
        """
        pass

    @classmethod
    def supports(cls, extension: str) -> bool:
        """Check if this extractor supports the given file extension.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            True if this extractor can handle the extension
        """
        ext = extension.lower()
        if not ext.startswith('.'):
            ext = f'.{ext}'
        return ext in cls.SUPPORTED_EXTENSIONS

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this extractor."""
        pass
