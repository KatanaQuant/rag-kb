"""Completeness/integrity reporting service

Generates integrity reports for API routes by wrapping
CompletenessAnalyzer with document/chunk repositories.
"""
from typing import Dict, List, Optional

from config import default_config
from operations.completeness_analyzer import CompletenessAnalyzer
from operations.completeness_repositories import DocumentRepository, ChunkRepository


class CompletenessReporter:
    """Generates completeness reports for API

    Wraps CompletenessAnalyzer with document/chunk repositories.
    """

    def __init__(self, progress_tracker, vector_store):
        self.tracker = progress_tracker
        self.store = vector_store
        self.db_path = default_config.database.path
        self._init_repos()

    def _init_repos(self):
        """Initialize repositories"""
        self.doc_repo = DocumentRepository(self.db_path)
        self.chunk_repo = ChunkRepository(self.db_path)

    def _create_analyzer(self) -> CompletenessAnalyzer:
        """Create analyzer with dependencies"""
        return CompletenessAnalyzer(
            document_repo=self.doc_repo,
            chunk_repo=self.chunk_repo,
            progress_tracker=self.tracker
        )

    def generate_report(self) -> Dict:
        """Generate completeness report"""
        # Preload all data in batch queries (fixes N+1)
        self.chunk_repo.preload_all_counts()
        if self.tracker:
            self.tracker.preload_all_progress()
        analyzer = self._create_analyzer()
        return analyzer.analyze_all()

    def _get_documents(self) -> List[Dict]:
        """Get all documents (for testing)"""
        return self.doc_repo.list_all()

    def analyze_single(self, file_path: str) -> Optional[Dict]:
        """Analyze single document"""
        analyzer = self._create_analyzer()
        report = analyzer.analyze_one(file_path)

        if not report:
            return None

        return {
            'file_path': report.file_path,
            'document_id': report.document_id,
            'is_complete': report.is_complete,
            'issues': [
                {
                    'issue': issue.issue.value if issue.issue else 'unknown',
                    'expected': issue.expected,
                    'actual': issue.actual,
                    'message': issue.message
                }
                for issue in report.issues
            ]
        }
