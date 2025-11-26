"""Security and validation API routes

Endpoints for managing rejected files, quarantine, and security scanning.
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import sqlite3
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from ingestion.progress import ProcessingProgressTracker
from services.quarantine_manager import QuarantineManager, QUARANTINE_CHECKS
from services.security_scan_cache import get_security_cache
from ingestion.file_type_validator import FileTypeValidator
from ingestion.validation_result import SecuritySeverity
from ingestion.helpers import FileHasher
from config import default_config

router = APIRouter(prefix="/api/security", tags=["security"])

# Thread pool for background scanning (prevents blocking event loop)
_scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="security_scan_")

# In-memory storage for scan jobs (persists during server lifetime)
_scan_jobs: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Response Models
# ============================================================================

class RejectedFileResponse(BaseModel):
    """Response model for rejected file"""
    file_path: str
    filename: str
    reason: str
    validation_check: Optional[str]
    rejected_at: str


class QuarantinedFileResponse(BaseModel):
    """Response model for quarantined file"""
    filename: str
    original_path: str
    reason: str
    validation_check: str
    file_hash: str
    quarantined_at: str
    can_restore: bool
    restored: bool
    restored_at: Optional[str]


class RestoreRequest(BaseModel):
    """Request model for restoring quarantined file"""
    filename: str
    force: bool = False


class PurgeRequest(BaseModel):
    """Request model for purging old quarantined files"""
    older_than_days: int
    dry_run: bool = False


class ScanRequest(BaseModel):
    """Request model for security scan"""
    auto_quarantine: bool = True  # Auto-quarantine CRITICAL files
    verbose: bool = False  # Include clean files in response


class SecurityFinding(BaseModel):
    """A security finding from scan"""
    file_path: str
    filename: str
    severity: str  # "CRITICAL" or "WARNING"
    reason: str
    validation_check: str
    file_hash: str
    matches: List[Dict[str, Any]] = []
    action_taken: Optional[str] = None  # "quarantined", "db_cleaned", None


class ScanResponse(BaseModel):
    """Response from security scan"""
    total_files: int
    clean_files: int
    critical_count: int
    warning_count: int
    critical_findings: List[SecurityFinding]
    warning_findings: List[SecurityFinding]
    auto_quarantine: bool
    message: str


class ScanJobResponse(BaseModel):
    """Response when starting a scan job"""
    job_id: str
    status: str  # "pending", "running", "completed", "failed"
    message: str


class ScanStatusResponse(BaseModel):
    """Response for scan job status"""
    job_id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: Optional[int] = None  # Files scanned so far
    total_files: Optional[int] = None
    result: Optional[ScanResponse] = None  # Present when completed
    error: Optional[str] = None  # Present when failed
    message: str


# ============================================================================
# Rejected Files Endpoints
# ============================================================================

@router.get("/rejected", response_model=List[RejectedFileResponse])
async def list_rejected_files():
    """List all files that failed validation

    Returns list of rejected files with:
    - File path and name
    - Rejection reason
    - Validation strategy that rejected it
    - Timestamp of rejection

    Example:
        GET /api/security/rejected

        Response:
        [
            {
                "file_path": "/app/knowledge_base/malware.pdf",
                "filename": "malware.pdf",
                "reason": "Validation failed (ExtensionMismatchStrategy): Executable masquerading as pdf",
                "validation_check": "ExtensionMismatchStrategy",
                "rejected_at": "2025-11-26T15:30:00Z"
            }
        ]
    """
    try:
        tracker = ProcessingProgressTracker(default_config.database.path)
        rejected = tracker.get_rejected_files()

        return [
            RejectedFileResponse(
                file_path=r.file_path,
                filename=Path(r.file_path).name,
                reason=r.error_message or "Unknown reason",
                validation_check=_extract_validation_check(r.error_message),
                rejected_at=r.last_updated or r.started_at or str(datetime.now())
            )
            for r in rejected
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list rejected files: {e}")


def _extract_validation_check(error_message: str) -> Optional[str]:
    """Extract validation check name from error message"""
    if not error_message:
        return None

    # Format: "Validation failed (StrategyName): reason"
    if "Validation failed (" in error_message:
        start = error_message.find("(") + 1
        end = error_message.find(")")
        if start > 0 and end > start:
            return error_message[start:end]

    return None


# ============================================================================
# Quarantine Management Endpoints
# ============================================================================

@router.get("/quarantine", response_model=List[QuarantinedFileResponse])
async def list_quarantined_files():
    """List all files in quarantine

    Returns list of quarantined files with metadata:
    - Original file path
    - Quarantine filename
    - Reason for quarantine
    - Validation check that quarantined it
    - File hash
    - Timestamps
    - Restore status

    Example:
        GET /api/security/quarantine

        Response:
        [
            {
                "filename": "malware.pdf.REJECTED",
                "original_path": "/app/knowledge_base/malware.pdf",
                "reason": "Executable masquerading as pdf",
                "validation_check": "ExtensionMismatchStrategy",
                "file_hash": "abc123...",
                "quarantined_at": "2025-11-26T15:30:00Z",
                "can_restore": true,
                "restored": false,
                "restored_at": null
            }
        ]
    """
    try:
        manager = QuarantineManager(default_config.paths.knowledge_base)
        quarantined = manager.list_quarantined()

        return [
            QuarantinedFileResponse(
                filename=Path(q.original_path).name + ".REJECTED",
                original_path=q.original_path,
                reason=q.reason,
                validation_check=q.validation_check,
                file_hash=q.file_hash,
                quarantined_at=q.quarantined_at,
                can_restore=q.can_restore,
                restored=q.restored,
                restored_at=q.restored_at
            )
            for q in quarantined
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list quarantined files: {e}")


@router.post("/quarantine/restore")
async def restore_quarantined_file(request: RestoreRequest):
    """Restore file from quarantine to original location

    Args:
        filename: Quarantined filename (e.g., "file.pdf.REJECTED")
        force: Force restore even if original path exists

    Returns:
        Success message

    Example:
        POST /api/security/quarantine/restore
        {
            "filename": "malware.pdf.REJECTED",
            "force": false
        }

        Response:
        {
            "success": true,
            "message": "File restored successfully",
            "original_path": "/app/knowledge_base/malware.pdf"
        }
    """
    try:
        manager = QuarantineManager(default_config.paths.knowledge_base)

        # Get metadata to find original path
        metadata = manager._read_metadata(request.filename)
        if not metadata:
            raise HTTPException(
                status_code=404,
                detail=f"Quarantined file not found: {request.filename}"
            )

        success = manager.restore_file(request.filename, force=request.force)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to restore file: {request.filename}"
            )

        return {
            "success": True,
            "message": "File restored successfully",
            "original_path": metadata.original_path
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore file: {e}")


@router.post("/quarantine/purge")
async def purge_old_quarantined_files(request: PurgeRequest):
    """Delete quarantined files older than specified days

    Args:
        older_than_days: Delete files quarantined more than this many days ago
        dry_run: If true, return what would be deleted without deleting

    Returns:
        Number of files purged or would be purged

    Example:
        POST /api/security/quarantine/purge
        {
            "older_than_days": 30,
            "dry_run": true
        }

        Response:
        {
            "success": true,
            "files_purged": 5,
            "dry_run": true,
            "message": "Would purge 5 files"
        }
    """
    try:
        manager = QuarantineManager(default_config.paths.knowledge_base)
        purged = manager.purge_old_files(request.older_than_days, dry_run=request.dry_run)

        return {
            "success": True,
            "files_purged": purged,
            "dry_run": request.dry_run,
            "message": f"{'Would purge' if request.dry_run else 'Purged'} {purged} files"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to purge files: {e}")


# ============================================================================
# Security Scanning Endpoint
# ============================================================================

# Number of parallel scan workers (I/O bound, so threads work well)
SCAN_WORKERS = 8


def _scan_single_file(file_path: Path, validator, hasher) -> dict:
    """Scan a single file and return result dict

    Thread-safe function for parallel scanning.
    Returns dict with scan result, not SecurityFinding (to avoid shared state).
    """
    try:
        result = validator.validate(file_path)
        file_hash = hasher.hash_file(file_path) if not result.is_valid or result.matches else None

        return {
            'file_path': file_path,
            'is_valid': result.is_valid,
            'severity': result.severity,
            'reason': result.reason,
            'validation_check': result.validation_check,
            'matches': result.matches,
            'file_hash': file_hash
        }
    except Exception as e:
        return {
            'file_path': file_path,
            'is_valid': False,
            'severity': SecuritySeverity.WARNING,
            'reason': f"Scan error: {e}",
            'validation_check': 'ScanError',
            'matches': [],
            'file_hash': None
        }


def _run_scan_job(job_id: str, auto_quarantine: bool, verbose: bool):
    """Background worker function for security scanning

    Runs in a separate thread to prevent blocking the event loop.
    Uses ThreadPoolExecutor for parallel file scanning (I/O bound).
    Updates _scan_jobs dict with progress and results.
    """
    try:
        _scan_jobs[job_id]['status'] = 'running'
        print(f"\n[Security] Starting security scan (job {job_id})...")

        kb_path = Path(default_config.paths.knowledge_base)
        validator = FileTypeValidator()
        quarantine = QuarantineManager(kb_path)
        hasher = FileHasher()
        db_path = default_config.database.path

        # Find all files in knowledge base
        all_files = []
        for ext in ['.pdf', '.md', '.markdown', '.docx', '.epub', '.py', '.java',
                    '.ts', '.tsx', '.js', '.jsx', '.cs', '.go', '.ipynb', '.txt']:
            all_files.extend(kb_path.rglob(f'*{ext}'))

        # Exclude quarantine directory and problematic directory
        all_files = [f for f in all_files
                     if '.quarantine' not in f.parts and 'problematic' not in f.parts]

        _scan_jobs[job_id]['total_files'] = len(all_files)
        _scan_jobs[job_id]['progress'] = 0

        if not all_files:
            _scan_jobs[job_id]['status'] = 'completed'
            _scan_jobs[job_id]['result'] = ScanResponse(
                total_files=0,
                clean_files=0,
                critical_count=0,
                warning_count=0,
                critical_findings=[],
                warning_findings=[],
                auto_quarantine=auto_quarantine,
                message="No files found in knowledge base"
            )
            return

        # Parallel scan using ThreadPoolExecutor (I/O bound work)
        clean_count = 0
        critical_findings = []
        warning_findings = []
        progress_counter = 0
        progress_lock = threading.Lock()

        def scan_with_progress(file_path):
            """Wrapper to update progress after each scan"""
            nonlocal progress_counter
            result = _scan_single_file(file_path, validator, hasher)
            with progress_lock:
                progress_counter += 1
                _scan_jobs[job_id]['progress'] = progress_counter
            return result

        # Use ThreadPoolExecutor for parallel scanning
        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
            results = list(executor.map(scan_with_progress, all_files))

        # Process results (sequential - handles quarantine which needs serialization)
        for scan_result in results:
            file_path = scan_result['file_path']
            is_valid = scan_result['is_valid']
            severity = scan_result['severity']
            matches = scan_result['matches']

            # Determine if this is truly CRITICAL (quarantinable)
            is_critical = (
                severity == SecuritySeverity.CRITICAL or
                (not is_valid and scan_result['validation_check'] in QUARANTINE_CHECKS)
            )

            if is_valid and not matches:
                clean_count += 1

            elif is_critical:
                file_hash = scan_result['file_hash'] or hasher.hash_file(file_path)
                action_taken = None

                # Auto-quarantine CRITICAL (sequential to avoid race conditions)
                if auto_quarantine:
                    quarantined = quarantine.quarantine_file(
                        file_path, scan_result['reason'],
                        scan_result['validation_check'], file_hash
                    )
                    if quarantined:
                        action_taken = "quarantined"
                        deleted = _delete_document_from_db(db_path, file_path)
                        if deleted > 0:
                            action_taken = f"quarantined, {deleted} chunks removed"

                critical_findings.append(SecurityFinding(
                    file_path=str(file_path),
                    filename=file_path.name,
                    severity="CRITICAL",
                    reason=scan_result['reason'],
                    validation_check=scan_result['validation_check'],
                    file_hash=file_hash,
                    matches=[
                        {"rule": m.rule_name, "severity": m.severity.value, "context": m.context}
                        for m in matches
                    ],
                    action_taken=action_taken
                ))

            elif severity == SecuritySeverity.WARNING or matches or not is_valid:
                file_hash = scan_result['file_hash'] or hasher.hash_file(file_path)
                warning_findings.append(SecurityFinding(
                    file_path=str(file_path),
                    filename=file_path.name,
                    severity="WARNING",
                    reason=scan_result['reason'],
                    validation_check=scan_result['validation_check'],
                    file_hash=file_hash,
                    matches=[
                        {"rule": m.rule_name, "severity": m.severity.value, "context": m.context}
                        for m in matches
                    ],
                    action_taken=None
                ))

        # Build message
        critical_msg = f"{len(critical_findings)} CRITICAL"
        if auto_quarantine and critical_findings:
            critical_msg += " (quarantined)"
        message = f"Scan complete: {critical_msg}, {len(warning_findings)} warnings"

        # Log completion summary
        print(f"\n[Security] ══════════════════════════════════════════════════════════════════")
        print(f"[Security] Scan complete: {len(all_files)} files scanned")
        print(f"[Security]   ✓ {clean_count} clean")
        if critical_findings:
            print(f"[Security]   ✗ {len(critical_findings)} CRITICAL (quarantined)" if auto_quarantine else f"[Security]   ✗ {len(critical_findings)} CRITICAL")
            for f in critical_findings:
                print(f"[Security]     - {f.filename}: {f.reason}")
        if warning_findings:
            print(f"[Security]   ⚠ {len(warning_findings)} warnings")
            for f in warning_findings:
                print(f"[Security]     - {f.filename}: {f.reason}")
        print(f"[Security] ══════════════════════════════════════════════════════════════════\n")

        _scan_jobs[job_id]['status'] = 'completed'
        _scan_jobs[job_id]['result'] = ScanResponse(
            total_files=len(all_files),
            clean_files=clean_count,
            critical_count=len(critical_findings),
            warning_count=len(warning_findings),
            critical_findings=critical_findings,
            warning_findings=warning_findings,
            auto_quarantine=auto_quarantine,
            message=message
        )

    except Exception as e:
        _scan_jobs[job_id]['status'] = 'failed'
        _scan_jobs[job_id]['error'] = str(e)


@router.post("/scan", response_model=ScanJobResponse)
async def scan_existing_files(request: ScanRequest = None):
    """Start a security scan of existing files in knowledge base

    **NON-BLOCKING**: This endpoint immediately returns a job ID. The scan
    runs in a background thread. Use GET /api/security/scan/{job_id} to
    check progress and get results.

    Performs retroactive security validation on all files in the knowledge base.
    Runs ClamAV virus scanning, hash blacklist checking, YARA pattern matching,
    and other security validations.

    Severity levels:
    - CRITICAL: Confirmed malware (ClamAV virus, hash blacklist, dangerous executables)
      - Auto-quarantined by default
      - Database entries removed when quarantined
    - WARNING: Suspicious patterns (YARA heuristics, non-dangerous validation failures)
      - Logged for manual review
      - Not auto-quarantined

    Args:
        auto_quarantine: If true (default), auto-quarantine CRITICAL files
        verbose: If true, return more detailed info

    Returns:
        Job ID to track scan progress

    Example:
        # Start a scan
        POST /api/security/scan
        {"auto_quarantine": true}

        Response:
        {"job_id": "abc123", "status": "pending", "message": "Scan started"}

        # Check progress
        GET /api/security/scan/abc123

        Response (in progress):
        {"job_id": "abc123", "status": "running", "progress": 500, "total_files": 2871, ...}

        Response (completed):
        {"job_id": "abc123", "status": "completed", "result": {...}, ...}

    Usage:
        # Start scan with auto-quarantine (recommended)
        curl -X POST http://localhost:8000/api/security/scan

        # Dry run - see what would be quarantined
        curl -X POST http://localhost:8000/api/security/scan \\
             -H "Content-Type: application/json" \\
             -d '{"auto_quarantine": false}'

        # Check progress
        curl http://localhost:8000/api/security/scan/{job_id}
    """
    if request is None:
        request = ScanRequest()

    # Generate unique job ID
    job_id = str(uuid.uuid4())[:8]

    # Initialize job status
    _scan_jobs[job_id] = {
        'status': 'pending',
        'progress': 0,
        'total_files': 0,
        'result': None,
        'error': None,
        'auto_quarantine': request.auto_quarantine,
        'started_at': datetime.now().isoformat()
    }

    # Submit to thread pool (non-blocking)
    _scan_executor.submit(_run_scan_job, job_id, request.auto_quarantine, request.verbose)

    return ScanJobResponse(
        job_id=job_id,
        status="pending",
        message=f"Scan started. Check progress at GET /api/security/scan/{job_id}"
    )


@router.get("/scan/{job_id}", response_model=ScanStatusResponse)
async def get_scan_status(job_id: str):
    """Get status and results of a security scan job

    Args:
        job_id: The job ID returned from POST /api/security/scan

    Returns:
        Current status, progress, and results (when complete)

    Example:
        GET /api/security/scan/abc123

        Response (in progress):
        {
            "job_id": "abc123",
            "status": "running",
            "progress": 1500,
            "total_files": 2871,
            "result": null,
            "error": null,
            "message": "Scanning: 1500/2871 files (52%)"
        }

        Response (completed):
        {
            "job_id": "abc123",
            "status": "completed",
            "progress": 2871,
            "total_files": 2871,
            "result": {
                "total_files": 2871,
                "clean_files": 2860,
                "critical_count": 2,
                ...
            },
            "error": null,
            "message": "Scan complete"
        }
    """
    if job_id not in _scan_jobs:
        raise HTTPException(status_code=404, detail=f"Scan job not found: {job_id}")

    job = _scan_jobs[job_id]
    status = job['status']
    progress = job.get('progress', 0)
    total = job.get('total_files', 0)

    # Build message based on status
    if status == 'pending':
        message = "Scan queued, waiting to start"
    elif status == 'running':
        pct = int(100 * progress / total) if total > 0 else 0
        message = f"Scanning: {progress}/{total} files ({pct}%)"
    elif status == 'completed':
        message = "Scan complete"
    elif status == 'failed':
        message = f"Scan failed: {job.get('error', 'Unknown error')}"
    else:
        message = f"Unknown status: {status}"

    return ScanStatusResponse(
        job_id=job_id,
        status=status,
        progress=progress,
        total_files=total,
        result=job.get('result'),
        error=job.get('error'),
        message=message
    )


@router.get("/scan", response_model=List[Dict[str, Any]])
async def list_scan_jobs():
    """List all security scan jobs

    Returns a list of all scan jobs with their current status.

    Example:
        GET /api/security/scan

        Response:
        [
            {
                "job_id": "abc123",
                "status": "completed",
                "progress": 2871,
                "total_files": 2871,
                "started_at": "2025-11-26T10:00:00"
            },
            {
                "job_id": "def456",
                "status": "running",
                "progress": 500,
                "total_files": 2871,
                "started_at": "2025-11-26T10:05:00"
            }
        ]
    """
    return [
        {
            "job_id": job_id,
            "status": job['status'],
            "progress": job.get('progress', 0),
            "total_files": job.get('total_files', 0),
            "started_at": job.get('started_at')
        }
        for job_id, job in _scan_jobs.items()
    ]


# ============================================================================
# Security Scan Cache Endpoints
# ============================================================================

class CacheStatsResponse(BaseModel):
    """Response model for cache statistics"""
    total_entries: int
    valid_count: int
    invalid_count: int
    oldest_entry: Optional[str]
    newest_entry: Optional[str]
    scanner_version: str


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """Get security scan cache statistics

    Returns statistics about the scan result cache:
    - Total cached entries
    - How many were valid vs invalid
    - Age of oldest/newest entries
    - Current scanner version

    Example:
        GET /api/security/cache/stats

        Response:
        {
            "total_entries": 2500,
            "valid_count": 2490,
            "invalid_count": 10,
            "oldest_entry": "2025-11-26T10:00:00",
            "newest_entry": "2025-11-26T12:30:00",
            "scanner_version": "1.0.0"
        }
    """
    cache = get_security_cache()
    stats = cache.stats()
    return CacheStatsResponse(**stats)


@router.delete("/cache")
async def clear_cache():
    """Clear all cached security scan results

    Use this when:
    - Scanner rules/signatures have been updated
    - You want to force a full re-scan
    - Cache has become corrupted

    Returns:
        Number of entries cleared

    Example:
        DELETE /api/security/cache

        Response:
        {
            "success": true,
            "entries_cleared": 2500,
            "message": "Cache cleared. Next scan will re-validate all files."
        }
    """
    cache = get_security_cache()
    cleared = cache.clear()
    return {
        "success": True,
        "entries_cleared": cleared,
        "message": "Cache cleared. Next scan will re-validate all files."
    }


def _delete_document_from_db(db_path: str, file_path: Path) -> int:
    """Delete document and its chunks from database

    Args:
        db_path: Path to database
        file_path: Path to the quarantined file

    Returns:
        Number of chunks deleted (0 if not found)
    """
    conn = sqlite3.connect(db_path)
    try:
        # Find the document by file path
        cursor = conn.execute(
            'SELECT id FROM documents WHERE file_path LIKE ?',
            (f'%{file_path.name}',)
        )
        row = cursor.fetchone()

        if not row:
            return 0

        doc_id = row[0]

        # Count chunks before deletion
        cursor = conn.execute(
            'SELECT COUNT(*) FROM chunks WHERE document_id = ?',
            (doc_id,)
        )
        chunk_count = cursor.fetchone()[0]

        # Delete chunks first (foreign key constraint)
        conn.execute('DELETE FROM chunks WHERE document_id = ?', (doc_id,))

        # Delete document
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))

        conn.commit()
        return chunk_count

    except Exception:
        return 0
    finally:
        conn.close()
