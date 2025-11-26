"""
Completeness Analyzer Service

Analyzes document completeness in knowledge base.

Following Sandi Metz patterns:
- Single Responsibility: Analyze completeness only
- Dependency Injection: Receive repositories
- Tell, Don't Ask: Delegate to strategies
"""
from typing import Dict, List, Optional

from ingestion.completeness_strategies import (
    ChunkCountStrategy,
    ProcessingStatusStrategy,
    DatabaseChunkStrategy
)
from ingestion.completeness_result import DocumentCompletenessReport


class CompletenessAnalyzer:
    """Analyzes document completeness across the knowledge base"""

    def __init__(self, document_repo, chunk_repo, progress_tracker=None):
        """Initialize with dependencies

        Args:
            document_repo: Repository for document metadata
            chunk_repo: Repository for chunk data
            progress_tracker: Optional progress tracking service
        """
        self.doc_repo = document_repo
        self.chunk_repo = chunk_repo
        self.tracker = progress_tracker
        self._init_strategies()

    def _init_strategies(self):
        """Initialize completeness check strategies"""
        self.chunk_strategy = ChunkCountStrategy()
        self.status_strategy = ProcessingStatusStrategy()
        self.db_chunk_strategy = DatabaseChunkStrategy()

    def analyze_all(self) -> Dict:
        """Analyze completeness of all documents

        Returns:
            Dict with total_documents, complete, incomplete, issues
        """
        documents = self.doc_repo.list_all()
        reports = self._analyze_documents(documents)
        return self._build_summary(reports)

    def analyze_one(self, file_path: str) -> Optional[DocumentCompletenessReport]:
        """Analyze completeness of single document

        Args:
            file_path: Path to document

        Returns:
            DocumentCompletenessReport or None if not found
        """
        doc = self.doc_repo.find_by_path(file_path)
        if not doc:
            return None

        return self._analyze_document(doc)

    def _analyze_documents(self, documents: List[Dict]) -> List[DocumentCompletenessReport]:
        """Analyze list of documents"""
        return [self._analyze_document(doc) for doc in documents]

    def _analyze_document(self, doc: Dict) -> DocumentCompletenessReport:
        """Analyze single document completeness"""
        doc_id = doc['id']
        file_path = doc['file_path']

        results = []

        # Check processing progress
        progress = self._get_progress(file_path)
        if progress:
            results.append(self.status_strategy.check(progress))
            results.append(self.chunk_strategy.check(progress))
        else:
            # No progress record = can't verify
            results.append(self._missing_progress_result())

        # Check database chunks exist
        chunk_count = self._get_chunk_count(doc_id)
        results.append(self.db_chunk_strategy.check(doc_id, chunk_count))

        return DocumentCompletenessReport.from_results(
            file_path=file_path,
            document_id=doc_id,
            results=results
        )

    def _get_progress(self, file_path: str):
        """Get progress for file path"""
        if not self.tracker:
            return None
        return self.tracker.get_progress(file_path)

    def _get_chunk_count(self, document_id: int) -> int:
        """Get chunk count for document from database"""
        if not self.chunk_repo:
            return 0
        return self.chunk_repo.count_by_document(document_id)

    def _missing_progress_result(self):
        """Create result for missing progress record"""
        from ingestion.completeness_result import (
            CompletenessResult, CompletenessIssue, Severity
        )
        return CompletenessResult.incomplete(
            issue=CompletenessIssue.PROCESSING_INCOMPLETE,
            expected=1,
            actual=0,
            severity=Severity.WARNING,
            message="No processing progress record found"
        )

    def _build_summary(self, reports: List[DocumentCompletenessReport]) -> Dict:
        """Build summary from reports"""
        complete = [r for r in reports if r.is_complete]
        incomplete = [r for r in reports if not r.is_complete]

        issues = []
        for report in incomplete:
            for issue in report.issues:
                issues.append({
                    'file_path': report.file_path,
                    'document_id': report.document_id,
                    'issue': issue.issue.value if issue.issue else 'unknown',
                    'expected': issue.expected,
                    'actual': issue.actual,
                    'message': issue.message
                })

        return {
            'total_documents': len(reports),
            'complete': len(complete),
            'incomplete': len(incomplete),
            'issues': issues
        }
