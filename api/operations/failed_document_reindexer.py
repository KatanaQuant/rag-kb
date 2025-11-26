"""Failed document reindexing service

Handles finding and re-queuing documents that failed or are incomplete.
"""
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field

from pipeline.indexing_queue import Priority


@dataclass
class ReindexCandidate:
    """A document candidate for reindexing"""
    file_path: str
    issue: str
    exists: bool = True


@dataclass
class ReindexResult:
    """Result of reindexing a document"""
    file_path: str
    filename: str
    success: bool
    error: Optional[str] = None


@dataclass
class ReindexSummary:
    """Summary of reindex operation"""
    documents_found: int
    documents_queued: int
    dry_run: bool
    results: List[ReindexResult] = field(default_factory=list)
    message: str = ""


class FailedDocumentReindexer:
    """Service to find and reindex failed/incomplete documents"""

    DEFAULT_ISSUE_TYPES = ['zero_chunks', 'processing_incomplete', 'missing_embeddings']
    MAX_RESULTS = 100

    def __init__(self, progress_tracker, vector_store, indexing_queue):
        self.progress_tracker = progress_tracker
        self.vector_store = vector_store
        self.indexing_queue = indexing_queue

    def reindex(self, issue_types: Optional[List[str]] = None,
                dry_run: bool = False) -> ReindexSummary:
        """Find and reindex failed documents"""
        candidates = self._find_candidates(issue_types)

        if not candidates:
            return self._empty_summary(dry_run)

        results = self._build_results(candidates)
        queued = 0 if dry_run else self._queue_documents(candidates)

        return self._build_summary(candidates, results, queued, dry_run)

    def _find_candidates(self, issue_types: Optional[List[str]]) -> List[ReindexCandidate]:
        """Find documents matching issue types"""
        from operations.completeness_reporter import CompletenessReporter

        reporter = CompletenessReporter(
            progress_tracker=self.progress_tracker,
            vector_store=self.vector_store
        )
        report = reporter.generate_report()

        allowed = issue_types or self.DEFAULT_ISSUE_TYPES
        return [
            ReindexCandidate(
                file_path=item['file_path'],
                issue=item['issue'],
                exists=Path(item['file_path']).exists()
            )
            for item in report.get('issues', [])
            if item['issue'] in allowed
        ]

    def _build_results(self, candidates: List[ReindexCandidate]) -> List[ReindexResult]:
        """Build result list for response"""
        return [
            ReindexResult(
                file_path=c.file_path,
                filename=Path(c.file_path).name,
                success=c.exists,
                error=None if c.exists else "File not found"
            )
            for c in candidates[:self.MAX_RESULTS]
        ]

    def _queue_documents(self, candidates: List[ReindexCandidate]) -> int:
        """Queue existing documents with HIGH priority"""
        if not self.indexing_queue:
            return 0

        queued = 0
        for candidate in candidates:
            if candidate.exists:
                self.indexing_queue.add(
                    Path(candidate.file_path),
                    priority=Priority.HIGH,
                    force=True
                )
                queued += 1
        return queued

    def _empty_summary(self, dry_run: bool) -> ReindexSummary:
        """Return empty summary when no candidates found"""
        return ReindexSummary(
            documents_found=0,
            documents_queued=0,
            dry_run=dry_run,
            results=[],
            message="No incomplete documents found"
        )

    def _build_summary(self, candidates: List[ReindexCandidate],
                       results: List[ReindexResult],
                       queued: int, dry_run: bool) -> ReindexSummary:
        """Build final summary"""
        action = "Would queue" if dry_run else "Queued"
        return ReindexSummary(
            documents_found=len(candidates),
            documents_queued=queued,
            dry_run=dry_run,
            results=results,
            message=f"{action} {len(candidates)} documents for reindexing with HIGH priority"
        )
