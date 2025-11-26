"""
Tests for Document Completeness Strategies

Following TDD Red/Green/Refactor:
- RED: Write these tests BEFORE implementing strategy classes
- GREEN: Implement strategy classes to make tests pass
- REFACTOR: Compose strategies in CompletenessAnalyzer

Goal: Detect incomplete documents via Strategy pattern (Sandi Metz style)
"""
import pytest
from unittest.mock import Mock, MagicMock
from ingestion.completeness_result import (
    CompletenessResult, CompletenessIssue, Severity, DocumentCompletenessReport
)


class TestCompletenessResultValueObject:
    """Test CompletenessResult immutable value object"""

    def test_complete_factory_creates_valid_result(self):
        """CompletenessResult.complete() should create complete result"""
        result = CompletenessResult.complete()
        assert result.is_complete is True
        assert result.issue is None

    def test_incomplete_factory_creates_result_with_issue(self):
        """CompletenessResult.incomplete() should capture issue details"""
        result = CompletenessResult.incomplete(
            issue=CompletenessIssue.CHUNK_COUNT_MISMATCH,
            expected=10,
            actual=5
        )
        assert result.is_complete is False
        assert result.issue == CompletenessIssue.CHUNK_COUNT_MISMATCH
        assert result.expected == 10
        assert result.actual == 5
        assert "10" in result.message and "5" in result.message

    def test_result_is_immutable(self):
        """CompletenessResult should be immutable (frozen dataclass)"""
        result = CompletenessResult.complete()
        with pytest.raises(Exception):  # FrozenInstanceError
            result.is_complete = False


class TestDocumentCompletenessReport:
    """Test DocumentCompletenessReport aggregation"""

    def test_from_results_all_complete(self):
        """Report should be complete when all checks pass"""
        results = [
            CompletenessResult.complete(),
            CompletenessResult.complete()
        ]
        report = DocumentCompletenessReport.from_results(
            file_path="/test/doc.pdf",
            document_id=1,
            results=results
        )
        assert report.is_complete is True
        assert len(report.issues) == 0

    def test_from_results_with_issues(self):
        """Report should capture all issues"""
        results = [
            CompletenessResult.complete(),
            CompletenessResult.incomplete(
                CompletenessIssue.CHUNK_COUNT_MISMATCH, 10, 5
            ),
            CompletenessResult.incomplete(
                CompletenessIssue.MISSING_EMBEDDINGS, 10, 8
            )
        ]
        report = DocumentCompletenessReport.from_results(
            file_path="/test/doc.pdf",
            document_id=1,
            results=results
        )
        assert report.is_complete is False
        assert len(report.issues) == 2


class TestChunkCountStrategy:
    """Test strategy for verifying chunk counts match expectations"""

    def test_passes_when_total_matches_processed(self):
        """ChunkCountStrategy should pass when total == processed"""
        from ingestion.completeness_strategies import ChunkCountStrategy

        strategy = ChunkCountStrategy()
        # Simulate progress record with matching counts
        progress = Mock(total_chunks=10, chunks_processed=10)
        result = strategy.check(progress)

        assert result.is_complete is True

    def test_fails_when_chunks_missing(self):
        """ChunkCountStrategy should fail when chunks are missing"""
        from ingestion.completeness_strategies import ChunkCountStrategy

        strategy = ChunkCountStrategy()
        progress = Mock(total_chunks=10, chunks_processed=5)
        result = strategy.check(progress)

        assert result.is_complete is False
        assert result.issue == CompletenessIssue.CHUNK_COUNT_MISMATCH
        assert result.expected == 10
        assert result.actual == 5

    def test_fails_when_zero_chunks(self):
        """ChunkCountStrategy should fail when document has zero chunks"""
        from ingestion.completeness_strategies import ChunkCountStrategy

        strategy = ChunkCountStrategy()
        progress = Mock(total_chunks=0, chunks_processed=0)
        result = strategy.check(progress)

        assert result.is_complete is False
        assert result.issue == CompletenessIssue.ZERO_CHUNKS

    def test_passes_when_total_not_set(self):
        """ChunkCountStrategy should pass if total_chunks not tracked yet"""
        from ingestion.completeness_strategies import ChunkCountStrategy

        strategy = ChunkCountStrategy()
        # total_chunks=None means we haven't started tracking
        progress = Mock(total_chunks=None, chunks_processed=5)
        result = strategy.check(progress)

        # Can't verify if we don't know expected - pass with warning
        assert result.is_complete is True


class TestEmbeddingCountStrategy:
    """Test strategy for verifying embeddings match chunks"""

    def test_passes_when_all_chunks_embedded(self):
        """EmbeddingCountStrategy should pass when all chunks have embeddings"""
        from ingestion.completeness_strategies import EmbeddingCountStrategy

        strategy = EmbeddingCountStrategy()
        # document has 10 chunks, 10 embeddings in vec_chunks
        result = strategy.check(chunk_count=10, embedding_count=10)

        assert result.is_complete is True

    def test_fails_when_embeddings_missing(self):
        """EmbeddingCountStrategy should fail when some embeddings missing"""
        from ingestion.completeness_strategies import EmbeddingCountStrategy

        strategy = EmbeddingCountStrategy()
        result = strategy.check(chunk_count=10, embedding_count=7)

        assert result.is_complete is False
        assert result.issue == CompletenessIssue.MISSING_EMBEDDINGS
        assert result.expected == 10
        assert result.actual == 7

    def test_passes_when_zero_chunks_zero_embeddings(self):
        """EmbeddingCountStrategy should handle empty documents"""
        from ingestion.completeness_strategies import EmbeddingCountStrategy

        strategy = EmbeddingCountStrategy()
        result = strategy.check(chunk_count=0, embedding_count=0)

        # Empty is technically "complete" - zero_chunks handled elsewhere
        assert result.is_complete is True


class TestProcessingStatusStrategy:
    """Test strategy for verifying processing completed"""

    def test_passes_when_status_completed(self):
        """ProcessingStatusStrategy should pass for completed status"""
        from ingestion.completeness_strategies import ProcessingStatusStrategy

        strategy = ProcessingStatusStrategy()
        progress = Mock(status='completed')
        result = strategy.check(progress)

        assert result.is_complete is True

    def test_fails_when_status_in_progress(self):
        """ProcessingStatusStrategy should fail for in_progress status"""
        from ingestion.completeness_strategies import ProcessingStatusStrategy

        strategy = ProcessingStatusStrategy()
        progress = Mock(status='in_progress')
        result = strategy.check(progress)

        assert result.is_complete is False
        assert result.issue == CompletenessIssue.PROCESSING_INCOMPLETE

    def test_fails_when_status_failed(self):
        """ProcessingStatusStrategy should fail for failed status"""
        from ingestion.completeness_strategies import ProcessingStatusStrategy

        strategy = ProcessingStatusStrategy()
        progress = Mock(status='failed', error_message='Extraction error')
        result = strategy.check(progress)

        assert result.is_complete is False
        assert result.severity == Severity.ERROR


class TestCompletenessAnalyzer:
    """Test CompletenessAnalyzer service that composes strategies"""

    @pytest.fixture
    def mock_progress_tracker(self):
        """Create mock progress tracker"""
        tracker = Mock()
        tracker.get_db_path.return_value = ":memory:"
        return tracker

    @pytest.fixture
    def mock_document_repo(self):
        """Create mock document repository"""
        repo = Mock()
        repo.list_all.return_value = [
            {'id': 1, 'file_path': '/test/doc1.pdf'},
            {'id': 2, 'file_path': '/test/doc2.pdf'}
        ]
        return repo

    @pytest.fixture
    def mock_chunk_repo(self):
        """Create mock chunk repository"""
        repo = Mock()
        repo.count_by_document.return_value = 10
        return repo

    def test_analyzes_all_documents(self, mock_document_repo, mock_chunk_repo, mock_progress_tracker):
        """CompletenessAnalyzer should analyze all documents"""
        from operations.completeness_analyzer import CompletenessAnalyzer

        analyzer = CompletenessAnalyzer(
            document_repo=mock_document_repo,
            chunk_repo=mock_chunk_repo,
            progress_tracker=mock_progress_tracker
        )
        report = analyzer.analyze_all()

        assert 'total_documents' in report
        assert report['total_documents'] == 2

    def test_identifies_complete_documents(self, mock_document_repo, mock_chunk_repo, mock_progress_tracker):
        """CompletenessAnalyzer should count complete documents"""
        from operations.completeness_analyzer import CompletenessAnalyzer

        # Setup: all documents complete
        mock_progress_tracker.get_progress.return_value = Mock(
            status='completed',
            total_chunks=10,
            chunks_processed=10
        )

        analyzer = CompletenessAnalyzer(
            document_repo=mock_document_repo,
            chunk_repo=mock_chunk_repo,
            progress_tracker=mock_progress_tracker
        )
        report = analyzer.analyze_all()

        assert report['complete'] == 2
        assert report['incomplete'] == 0

    def test_identifies_incomplete_documents(self, mock_document_repo, mock_chunk_repo, mock_progress_tracker):
        """CompletenessAnalyzer should identify and list incomplete documents"""
        from operations.completeness_analyzer import CompletenessAnalyzer

        # Setup: one document incomplete
        mock_progress_tracker.get_progress.side_effect = [
            Mock(status='completed', total_chunks=10, chunks_processed=10),
            Mock(status='completed', total_chunks=10, chunks_processed=5)  # incomplete
        ]

        analyzer = CompletenessAnalyzer(
            document_repo=mock_document_repo,
            chunk_repo=mock_chunk_repo,
            progress_tracker=mock_progress_tracker
        )
        report = analyzer.analyze_all()

        assert report['complete'] == 1
        assert report['incomplete'] == 1
        assert len(report['issues']) == 1
        assert report['issues'][0]['file_path'] == '/test/doc2.pdf'

    def test_handles_missing_progress_record(self, mock_document_repo, mock_chunk_repo, mock_progress_tracker):
        """CompletenessAnalyzer should handle documents without progress records"""
        from operations.completeness_analyzer import CompletenessAnalyzer

        mock_progress_tracker.get_progress.return_value = None

        analyzer = CompletenessAnalyzer(
            document_repo=mock_document_repo,
            chunk_repo=mock_chunk_repo,
            progress_tracker=mock_progress_tracker
        )
        report = analyzer.analyze_all()

        # Missing progress = can't verify = marked incomplete
        assert report['incomplete'] == 2


class TestDatabaseChunkStrategy:
    """Test strategy for verifying chunks exist in database"""

    def test_passes_when_chunks_exist(self):
        """DatabaseChunkStrategy should pass when document has chunks"""
        from ingestion.completeness_strategies import DatabaseChunkStrategy

        strategy = DatabaseChunkStrategy()
        result = strategy.check(document_id=1, chunk_count=10)

        assert result.is_complete is True

    def test_fails_when_no_chunks_in_db(self):
        """DatabaseChunkStrategy should fail when document has no chunks"""
        from ingestion.completeness_strategies import DatabaseChunkStrategy

        strategy = DatabaseChunkStrategy()
        result = strategy.check(document_id=1, chunk_count=0)

        assert result.is_complete is False
        assert result.issue == CompletenessIssue.MISSING_EMBEDDINGS
        assert "no chunks" in result.message.lower()


class TestPDFIntegrityStrategy:
    """Test strategy for PDF integrity validation"""

    def test_passes_for_non_pdf_files(self):
        """PDFIntegrityStrategy should pass for non-PDF files"""
        from ingestion.completeness_strategies import PDFIntegrityStrategy

        strategy = PDFIntegrityStrategy()
        result = strategy.check(file_path="/test/document.docx")

        assert result.is_complete is True

    def test_fails_for_corrupted_pdf(self, tmp_path):
        """PDFIntegrityStrategy should fail for corrupted PDFs"""
        from ingestion.completeness_strategies import PDFIntegrityStrategy

        # Create corrupted PDF (missing EOF)
        pdf_path = tmp_path / "corrupted.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nsome content but no EOF")

        strategy = PDFIntegrityStrategy()
        result = strategy.check(file_path=str(pdf_path))

        assert result.is_complete is False
        assert result.issue == CompletenessIssue.PDF_INTEGRITY_FAILURE
        assert "integrity" in result.message.lower()

    def test_passes_for_valid_pdf(self, tmp_path):
        """PDFIntegrityStrategy should pass for valid PDFs"""
        from ingestion.completeness_strategies import PDFIntegrityStrategy

        # Create minimal valid PDF (from test_pdf_integrity.py fixture)
        pdf_path = tmp_path / "valid.pdf"
        content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
410
%%EOF
"""
        pdf_path.write_bytes(content)

        strategy = PDFIntegrityStrategy()
        result = strategy.check(file_path=str(pdf_path))

        assert result.is_complete is True


class TestCompletenessStrategyComposition:
    """Test that strategies compose correctly"""

    def test_all_strategies_implement_check_method(self):
        """All strategies should have check() method"""
        from ingestion.completeness_strategies import (
            ChunkCountStrategy,
            EmbeddingCountStrategy,
            ProcessingStatusStrategy,
            DatabaseChunkStrategy
        )

        strategies = [
            ChunkCountStrategy(),
            EmbeddingCountStrategy(),
            ProcessingStatusStrategy(),
            DatabaseChunkStrategy()
        ]

        for strategy in strategies:
            assert hasattr(strategy, 'check')
            assert callable(getattr(strategy, 'check'))

    def test_strategies_return_completeness_result(self):
        """All strategies should return CompletenessResult"""
        from ingestion.completeness_strategies import ChunkCountStrategy

        strategy = ChunkCountStrategy()
        progress = Mock(total_chunks=10, chunks_processed=10)
        result = strategy.check(progress)

        assert isinstance(result, CompletenessResult)
