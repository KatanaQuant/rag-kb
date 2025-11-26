"""
Document completeness routes

Provides API endpoints for checking document completeness.

Following Sandi Metz patterns:
- Single Responsibility: completeness reporting only
- Dependency Injection: receive services via Request
"""
from fastapi import APIRouter, Request, HTTPException
from typing import Dict, List, Optional
import sqlite3

from config import default_config
from api_services.completeness_analyzer import CompletenessAnalyzer


router = APIRouter()


class DocumentRepository:
    """Simple repository for document queries

    Used by CompletenessReporter to list documents.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def list_all(self) -> List[Dict]:
        """List all documents"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT id, file_path, file_hash, indexed_at
            FROM documents
            ORDER BY indexed_at DESC
        """)
        documents = [self._row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        return documents

    def find_by_path(self, file_path: str) -> Optional[Dict]:
        """Find document by path"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT id, file_path, file_hash, indexed_at FROM documents WHERE file_path = ?",
            (file_path,)
        )
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    @staticmethod
    def _row_to_dict(row) -> Dict:
        """Convert row to dict"""
        return {
            'id': row[0],
            'file_path': row[1],
            'file_hash': row[2],
            'indexed_at': row[3]
        }


class ChunkRepository:
    """Simple repository for chunk queries"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def count_by_document(self, document_id: int) -> int:
        """Count chunks for document"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            (document_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count


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


@router.get("/documents/completeness")
async def get_completeness_report(request: Request):
    """Get document completeness report

    Returns summary of document completeness across the knowledge base.

    Response includes:
    - total_documents: Total indexed documents
    - complete: Documents passing all checks
    - incomplete: Documents with issues
    - issues: List of specific issues found
    """
    try:
        app_state = request.app.state.app_state
        reporter = CompletenessReporter(
            progress_tracker=app_state.core.progress_tracker,
            vector_store=app_state.core.async_vector_store
        )
        return reporter.generate_report()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate completeness report: {str(e)}"
        )


@router.get("/documents/completeness/{file_path:path}")
async def get_document_completeness(file_path: str, request: Request):
    """Get completeness status for specific document

    Args:
        file_path: Full path to document

    Returns:
        Completeness status and any issues found
    """
    try:
        app_state = request.app.state.app_state
        reporter = CompletenessReporter(
            progress_tracker=app_state.core.progress_tracker,
            vector_store=app_state.core.async_vector_store
        )
        result = reporter.analyze_single(file_path)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {file_path}"
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze document: {str(e)}"
        )
