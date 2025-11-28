"""
Completeness verification strategies

Following Sandi Metz patterns:
- Strategy Pattern for composable checks
- Single Responsibility per strategy
- Tell, Don't Ask principle
"""
from abc import ABC, abstractmethod
from typing import Optional

from ingestion.completeness_result import (
    CompletenessResult, CompletenessIssue, Severity
)


class CompletenessStrategy(ABC):
    """Base class for completeness check strategies"""

    @abstractmethod
    def check(self, *args, **kwargs) -> CompletenessResult:
        """Perform completeness check"""
        pass


class ChunkCountStrategy(CompletenessStrategy):
    """Verify chunk counts match expectations

    Checks that total_chunks == chunks_processed.
    """

    def check(self, progress) -> CompletenessResult:
        """Check chunk count consistency

        Args:
            progress: ProcessingProgress object with total_chunks, chunks_processed
        """
        total = progress.total_chunks
        processed = progress.chunks_processed

        # If total not tracked yet, can't verify - pass
        if total is None:
            return CompletenessResult.complete()

        # Zero chunks is suspicious
        if total == 0 and processed == 0:
            return CompletenessResult.incomplete(
                issue=CompletenessIssue.ZERO_CHUNKS,
                expected=1,  # At least 1 expected
                actual=0,
                severity=Severity.WARNING,
                message="Document produced zero chunks"
            )

        # Mismatch between total and processed
        if total != processed:
            return CompletenessResult.incomplete(
                issue=CompletenessIssue.CHUNK_COUNT_MISMATCH,
                expected=total,
                actual=processed,
                severity=Severity.WARNING,
                message=f"Expected {total} chunks, only {processed} processed"
            )

        return CompletenessResult.complete()


class EmbeddingCountStrategy(CompletenessStrategy):
    """Verify embeddings match chunk count

    Checks that all chunks have corresponding embeddings.
    """

    def check(self, chunk_count: int, embedding_count: int) -> CompletenessResult:
        """Check embedding count matches chunks

        Args:
            chunk_count: Number of chunks in document
            embedding_count: Number of embeddings in vec_chunks
        """
        # Empty is technically complete (zero_chunks handled elsewhere)
        if chunk_count == 0 and embedding_count == 0:
            return CompletenessResult.complete()

        if chunk_count != embedding_count:
            return CompletenessResult.incomplete(
                issue=CompletenessIssue.MISSING_EMBEDDINGS,
                expected=chunk_count,
                actual=embedding_count,
                severity=Severity.WARNING,
                message=f"Expected {chunk_count} embeddings, found {embedding_count}"
            )

        return CompletenessResult.complete()


class ProcessingStatusStrategy(CompletenessStrategy):
    """Verify processing completed successfully

    Checks status field for completion.
    """

    def check(self, progress) -> CompletenessResult:
        """Check processing status

        Args:
            progress: ProcessingProgress object with status, error_message
        """
        status = progress.status

        if status == 'completed':
            return CompletenessResult.complete()

        if status == 'failed':
            error_msg = getattr(progress, 'error_message', None) or 'Unknown error'
            return CompletenessResult.incomplete(
                issue=CompletenessIssue.PROCESSING_INCOMPLETE,
                expected=1,
                actual=0,
                severity=Severity.ERROR,
                message=f"Processing failed: {error_msg}"
            )

        # in_progress or other status
        return CompletenessResult.incomplete(
            issue=CompletenessIssue.PROCESSING_INCOMPLETE,
            expected=1,
            actual=0,
            severity=Severity.WARNING,
            message=f"Processing not complete (status: {status})"
        )


class BlankPageStrategy(CompletenessStrategy):
    """Detect blank or near-empty pages

    Flags pages with insufficient content.
    """

    def __init__(self, min_chars: int = 50):
        self.min_chars = min_chars

    def check(self, pages: list) -> CompletenessResult:
        """Check for blank pages

        Args:
            pages: List of (text, page_num) tuples
        """
        blank_pages = []
        for text, page_num in pages:
            if len(text.strip()) < self.min_chars:
                blank_pages.append(page_num)

        if blank_pages:
            return CompletenessResult.incomplete(
                issue=CompletenessIssue.PAGE_COUNT_MISMATCH,
                expected=len(pages),
                actual=len(pages) - len(blank_pages),
                severity=Severity.WARNING,
                message=f"Found {len(blank_pages)} blank/sparse pages: {blank_pages[:5]}"
            )

        return CompletenessResult.complete()


class CharDistributionStrategy(CompletenessStrategy):
    """Detect anomalous content distribution

    Flags pages that are statistical outliers.
    """

    def __init__(self, std_dev_threshold: float = 2.0):
        self.threshold = std_dev_threshold

    def check(self, pages: list) -> CompletenessResult:
        """Check for content distribution anomalies

        Args:
            pages: List of (text, page_num) tuples
        """
        if len(pages) < 3:
            return CompletenessResult.complete()

        char_counts = [len(text) for text, _ in pages]
        stats = self._compute_stats(char_counts)
        if stats is None:
            return CompletenessResult.complete()

        outliers = self._find_outliers(pages, char_counts, stats)
        return self._build_result(len(pages), outliers)

    def _compute_stats(self, char_counts: list) -> tuple | None:
        """Compute mean and std_dev, returns None if std_dev is zero"""
        mean = sum(char_counts) / len(char_counts)
        variance = sum((c - mean) ** 2 for c in char_counts) / len(char_counts)
        std_dev = variance ** 0.5
        return (mean, std_dev) if std_dev > 0 else None

    def _find_outliers(
        self, pages: list, char_counts: list, stats: tuple
    ) -> list:
        """Find pages significantly below average"""
        mean, std_dev = stats
        outliers = []
        for (_, page_num), count in zip(pages, char_counts):
            z_score = abs(count - mean) / std_dev
            if z_score > self.threshold and count < mean:
                outliers.append((page_num, count))
        return outliers

    def _build_result(self, page_count: int, outliers: list) -> CompletenessResult:
        """Build result based on outliers found"""
        if not outliers:
            return CompletenessResult.complete()
        return CompletenessResult.incomplete(
            issue=CompletenessIssue.PAGE_COUNT_MISMATCH,
            expected=page_count,
            actual=page_count - len(outliers),
            severity=Severity.WARNING,
            message=f"Found {len(outliers)} outlier pages with low content"
        )


class DatabaseChunkStrategy(CompletenessStrategy):
    """Verify document has chunks in database

    Checks that document has at least one chunk stored.
    Documents with 0 chunks are orphans (metadata exists but no content).
    """

    def check(self, document_id: int, chunk_count: int) -> CompletenessResult:
        """Check if document has chunks in database

        Args:
            document_id: ID of document in documents table
            chunk_count: Number of chunks in chunks table for this document
        """
        if chunk_count > 0:
            return CompletenessResult.complete()

        return CompletenessResult.incomplete(
            issue=CompletenessIssue.MISSING_EMBEDDINGS,
            expected=1,
            actual=0,
            severity=Severity.ERROR,
            message=f"Document {document_id} has no chunks in database (orphan record)"
        )


class PDFIntegrityStrategy(CompletenessStrategy):
    """Verify PDF file integrity before processing

    Detects corrupted, truncated, or partially downloaded PDFs.
    This is CRITICAL for preventing silent failures where broken PDFs
    produce zero chunks without clear error messages.
    """

    def check(self, file_path: str) -> CompletenessResult:
        """Check PDF file integrity

        Args:
            file_path: Path to PDF file

        Returns:
            CompletenessResult indicating if PDF passes integrity checks
        """
        from pathlib import Path
        from ingestion.pdf_integrity import PDFIntegrityValidator

        path = Path(file_path)

        # Only check PDFs
        if path.suffix.lower() != '.pdf':
            return CompletenessResult.complete()

        # Run integrity validation
        result = PDFIntegrityValidator.validate(path)

        if result.is_valid:
            return CompletenessResult.complete()

        # PDF failed integrity check
        return CompletenessResult.incomplete(
            issue=CompletenessIssue.PDF_INTEGRITY_FAILURE,
            expected=1,
            actual=0,
            severity=Severity.ERROR,
            message=f"PDF integrity check failed: {result.error}"
        )
