"""
Completeness result value objects

Following Sandi Metz patterns - immutable dataclasses, no primitive obsession.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CompletenessIssue(Enum):
    """Types of completeness issues"""
    CHUNK_COUNT_MISMATCH = "chunk_count_mismatch"
    MISSING_EMBEDDINGS = "missing_embeddings"
    PAGE_COUNT_MISMATCH = "page_count_mismatch"
    ZERO_CHUNKS = "zero_chunks"
    PROCESSING_INCOMPLETE = "processing_incomplete"
    PDF_INTEGRITY_FAILURE = "pdf_integrity_failure"


class Severity(Enum):
    """Issue severity levels"""
    ERROR = "error"      # Document unusable
    WARNING = "warning"  # Document usable but degraded


@dataclass(frozen=True)
class CompletenessResult:
    """Result of a single completeness check

    Immutable value object following Sandi Metz patterns.
    """
    is_complete: bool
    issue: Optional[CompletenessIssue] = None
    expected: Optional[int] = None
    actual: Optional[int] = None
    severity: Severity = Severity.WARNING
    message: str = ""

    @classmethod
    def complete(cls) -> 'CompletenessResult':
        """Factory for complete result"""
        return cls(is_complete=True)

    @classmethod
    def incomplete(cls, issue: CompletenessIssue, expected: int, actual: int,
                   severity: Severity = Severity.WARNING,
                   message: str = "") -> 'CompletenessResult':
        """Factory for incomplete result"""
        return cls(
            is_complete=False,
            issue=issue,
            expected=expected,
            actual=actual,
            severity=severity,
            message=message or f"Expected {expected}, got {actual}"
        )


@dataclass(frozen=True)
class DocumentCompletenessReport:
    """Completeness report for a single document

    Aggregates multiple check results.
    """
    file_path: str
    document_id: int
    is_complete: bool
    issues: tuple  # Tuple of CompletenessResult for immutability

    @classmethod
    def from_results(cls, file_path: str, document_id: int,
                     results: list) -> 'DocumentCompletenessReport':
        """Factory from list of check results"""
        issues = tuple(r for r in results if not r.is_complete)
        return cls(
            file_path=file_path,
            document_id=document_id,
            is_complete=len(issues) == 0,
            issues=issues
        )
