"""Security scanner for batch file scanning

Extracted from routes/security.py to follow Single Responsibility Principle.
Each method is focused and under 20 lines per Sandi Metz guidelines.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import threading
import sqlite3

from ingestion.file_type_validator import FileTypeValidator
from ingestion.validation_result import SecuritySeverity
from ingestion.helpers import FileHasher
from pipeline.quarantine_manager import QuarantineManager, QUARANTINE_CHECKS


SCAN_WORKERS = 8
SUPPORTED_EXTENSIONS = [
    '.pdf', '.md', '.markdown', '.docx', '.epub', '.py', '.java',
    '.ts', '.tsx', '.js', '.jsx', '.cs', '.go', '.ipynb', '.txt'
]


@dataclass
class ScanResult:
    """Result of scanning a single file"""
    file_path: Path
    is_valid: bool
    severity: SecuritySeverity
    reason: str
    validation_check: str
    matches: List[Any] = field(default_factory=list)
    file_hash: Optional[str] = None


@dataclass
class ScanProgress:
    """Tracks scan progress for job status updates"""
    total_files: int = 0
    scanned: int = 0
    clean: int = 0
    critical: int = 0
    warnings: int = 0


@dataclass
class SecurityFinding:
    """A security finding from scan"""
    file_path: str
    filename: str
    severity: str
    reason: str
    validation_check: str
    file_hash: str
    matches: List[Dict[str, Any]] = field(default_factory=list)
    action_taken: Optional[str] = None


@dataclass
class ScanSummary:
    """Summary of a completed security scan"""
    total_files: int
    clean_files: int
    critical_findings: List[SecurityFinding]
    warning_findings: List[SecurityFinding]
    auto_quarantine: bool
    message: str


class FileCollector:
    """Collects files for scanning from knowledge base"""

    def __init__(self, kb_path: Path):
        self.kb_path = kb_path

    def collect(self) -> List[Path]:
        """Collect all scannable files, excluding quarantine"""
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(self.kb_path.rglob(f'*{ext}'))
        return self._filter_excluded(files)

    def _filter_excluded(self, files: List[Path]) -> List[Path]:
        """Remove quarantine and problematic directories"""
        return [f for f in files
                if '.quarantine' not in f.parts
                and 'problematic' not in f.parts]


class FileScannerWorker:
    """Scans individual files for security issues"""

    def __init__(self):
        self.validator = FileTypeValidator()
        self.hasher = FileHasher()

    def scan(self, file_path: Path) -> ScanResult:
        """Scan a single file and return result"""
        try:
            result = self.validator.validate(file_path)
            file_hash = self._compute_hash_if_needed(file_path, result)
            return ScanResult(
                file_path=file_path,
                is_valid=result.is_valid,
                severity=result.severity,
                reason=result.reason,
                validation_check=result.validation_check,
                matches=result.matches,
                file_hash=file_hash
            )
        except Exception as e:
            return self._error_result(file_path, e)

    def _compute_hash_if_needed(self, file_path: Path, result) -> Optional[str]:
        """Only compute hash for invalid or matched files"""
        if not result.is_valid or result.matches:
            return self.hasher.hash_file(file_path)
        return None

    def _error_result(self, file_path: Path, error: Exception) -> ScanResult:
        """Create error result for failed scans"""
        return ScanResult(
            file_path=file_path,
            is_valid=False,
            severity=SecuritySeverity.WARNING,
            reason=f"Scan error: {error}",
            validation_check='ScanError'
        )


class ResultClassifier:
    """Classifies scan results into clean/critical/warning"""

    def is_critical(self, result: ScanResult) -> bool:
        """Determine if result is critical (quarantinable)"""
        if result.severity == SecuritySeverity.CRITICAL:
            return True
        if not result.is_valid and result.validation_check in QUARANTINE_CHECKS:
            return True
        return False

    def is_clean(self, result: ScanResult) -> bool:
        """Determine if result is clean (no issues)"""
        return result.is_valid and not result.matches

    def is_warning(self, result: ScanResult) -> bool:
        """Determine if result is a warning"""
        if self.is_clean(result) or self.is_critical(result):
            return False
        return (result.severity == SecuritySeverity.WARNING
                or result.matches
                or not result.is_valid)


class QuarantineHandler:
    """Handles quarantine operations for critical findings"""

    def __init__(self, kb_path: Path, db_path: str):
        self.quarantine = QuarantineManager(kb_path)
        self.db_path = db_path
        self.hasher = FileHasher()

    def quarantine_file(self, result: ScanResult) -> Optional[str]:
        """Quarantine file and clean DB, return action description"""
        file_hash = result.file_hash or self.hasher.hash_file(result.file_path)

        quarantined = self.quarantine.quarantine_file(
            result.file_path,
            result.reason,
            result.validation_check,
            file_hash
        )

        if not quarantined:
            return None

        deleted = self._delete_from_db(result.file_path)
        if deleted > 0:
            return f"quarantined, {deleted} chunks removed"
        return "quarantined"

    def _delete_from_db(self, file_path: Path) -> int:
        """Delete document and chunks from database"""
        conn = sqlite3.connect(self.db_path)
        try:
            doc_id = self._find_document(conn, file_path)
            if not doc_id:
                return 0
            return self._delete_document(conn, doc_id)
        except Exception:
            return 0
        finally:
            conn.close()

    def _find_document(self, conn, file_path: Path) -> Optional[int]:
        """Find document ID by file path"""
        cursor = conn.execute(
            'SELECT id FROM documents WHERE file_path LIKE ?',
            (f'%{file_path.name}',)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def _delete_document(self, conn, doc_id: int) -> int:
        """Delete document and return chunk count"""
        cursor = conn.execute(
            'SELECT COUNT(*) FROM chunks WHERE document_id = ?', (doc_id,)
        )
        chunk_count = cursor.fetchone()[0]
        conn.execute('DELETE FROM chunks WHERE document_id = ?', (doc_id,))
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
        return chunk_count


class FindingBuilder:
    """Builds SecurityFinding objects from scan results"""

    def __init__(self):
        self.hasher = FileHasher()

    def build(self, result: ScanResult, severity: str,
              action_taken: Optional[str] = None) -> SecurityFinding:
        """Build a SecurityFinding from a ScanResult"""
        file_hash = result.file_hash or self.hasher.hash_file(result.file_path)
        return SecurityFinding(
            file_path=str(result.file_path),
            filename=result.file_path.name,
            severity=severity,
            reason=result.reason,
            validation_check=result.validation_check,
            file_hash=file_hash,
            matches=self._format_matches(result.matches),
            action_taken=action_taken
        )

    def _format_matches(self, matches: List[Any]) -> List[Dict[str, Any]]:
        """Format match objects to dicts"""
        return [
            {"rule": m.rule_name, "severity": m.severity.value, "context": m.context}
            for m in matches
        ]


class ScanLogger:
    """Logs scan progress and results"""

    def log_start(self, job_id: str):
        print(f"\n[Security] Starting security scan (job {job_id})...")

    def log_completion(self, summary: ScanSummary):
        print(f"\n[Security] {'=' * 70}")
        print(f"[Security] Scan complete: {summary.total_files} files scanned")
        print(f"[Security]   + {summary.clean_files} clean")
        self._log_critical(summary)
        self._log_warnings(summary)
        print(f"[Security] {'=' * 70}\n")

    def _log_critical(self, summary: ScanSummary):
        if not summary.critical_findings:
            return
        action = "(quarantined)" if summary.auto_quarantine else ""
        print(f"[Security]   x {len(summary.critical_findings)} CRITICAL {action}")
        for f in summary.critical_findings:
            print(f"[Security]     - {f.filename}: {f.reason}")

    def _log_warnings(self, summary: ScanSummary):
        if not summary.warning_findings:
            return
        print(f"[Security]   ! {len(summary.warning_findings)} warnings")
        for f in summary.warning_findings:
            print(f"[Security]     - {f.filename}: {f.reason}")


class SecurityScanner:
    """Orchestrates security scanning of knowledge base files

    Coordinates file collection, parallel scanning, result classification,
    quarantine handling, and logging. Each component follows SRP.
    """

    def __init__(self, kb_path: Path, db_path: str):
        self.collector = FileCollector(kb_path)
        self.worker = FileScannerWorker()
        self.classifier = ResultClassifier()
        self.quarantine_handler = QuarantineHandler(kb_path, db_path)
        self.finding_builder = FindingBuilder()
        self.logger = ScanLogger()

    def scan(self, job_id: str, auto_quarantine: bool,
             progress_callback=None) -> ScanSummary:
        """Execute full security scan"""
        self.logger.log_start(job_id)

        files = self.collector.collect()
        if not files:
            return self._empty_summary(auto_quarantine)

        results = self._scan_files_parallel(files, progress_callback)
        summary = self._process_results(results, auto_quarantine)

        self.logger.log_completion(summary)
        return summary

    def _scan_files_parallel(self, files: List[Path],
                              progress_callback=None) -> List[ScanResult]:
        """Scan files in parallel using thread pool"""
        progress_lock = threading.Lock()
        scanned = [0]  # Mutable container for closure

        def scan_with_progress(file_path: Path) -> ScanResult:
            result = self.worker.scan(file_path)
            if progress_callback:
                with progress_lock:
                    scanned[0] += 1
                    progress_callback(scanned[0])
            return result

        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
            return list(executor.map(scan_with_progress, files))

    def _process_results(self, results: List[ScanResult],
                         auto_quarantine: bool) -> ScanSummary:
        """Classify results and handle quarantine"""
        clean_count = 0
        critical_findings = []
        warning_findings = []

        for result in results:
            if self.classifier.is_clean(result):
                clean_count += 1
            elif self.classifier.is_critical(result):
                finding = self._handle_critical(result, auto_quarantine)
                critical_findings.append(finding)
            elif self.classifier.is_warning(result):
                finding = self.finding_builder.build(result, "WARNING")
                warning_findings.append(finding)

        return self._build_summary(
            len(results), clean_count,
            critical_findings, warning_findings,
            auto_quarantine
        )

    def _handle_critical(self, result: ScanResult,
                         auto_quarantine: bool) -> SecurityFinding:
        """Handle critical finding with optional quarantine"""
        action_taken = None
        if auto_quarantine:
            action_taken = self.quarantine_handler.quarantine_file(result)
        return self.finding_builder.build(result, "CRITICAL", action_taken)

    def _build_summary(self, total: int, clean: int,
                       critical: List[SecurityFinding],
                       warnings: List[SecurityFinding],
                       auto_quarantine: bool) -> ScanSummary:
        """Build final scan summary"""
        message = self._build_message(critical, warnings, auto_quarantine)
        return ScanSummary(
            total_files=total,
            clean_files=clean,
            critical_findings=critical,
            warning_findings=warnings,
            auto_quarantine=auto_quarantine,
            message=message
        )

    def _build_message(self, critical: List[SecurityFinding],
                       warnings: List[SecurityFinding],
                       auto_quarantine: bool) -> str:
        """Build human-readable summary message"""
        critical_msg = f"{len(critical)} CRITICAL"
        if auto_quarantine and critical:
            critical_msg += " (quarantined)"
        return f"Scan complete: {critical_msg}, {len(warnings)} warnings"

    def _empty_summary(self, auto_quarantine: bool) -> ScanSummary:
        """Return empty summary when no files found"""
        return ScanSummary(
            total_files=0,
            clean_files=0,
            critical_findings=[],
            warning_findings=[],
            auto_quarantine=auto_quarantine,
            message="No files found in knowledge base"
        )
