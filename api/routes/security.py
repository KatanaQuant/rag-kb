"""Security and validation API routes

Endpoints for managing rejected files, quarantine, and security scanning.
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor

from ingestion.progress import ProcessingProgressTracker
from pipeline.quarantine_manager import QuarantineManager
from pipeline.security_scan_cache import get_security_cache
from pipeline.security_scanner import SecurityScanner
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


def _finding_from_summary(f) -> SecurityFinding:
    """Convert scanner finding to API response model"""
    return SecurityFinding(
        file_path=f.file_path,
        filename=f.filename,
        severity=f.severity,
        reason=f.reason,
        validation_check=f.validation_check,
        file_hash=f.file_hash,
        matches=f.matches,
        action_taken=f.action_taken
    )


def _build_threats_from_result(result) -> List[Dict[str, Any]]:
    """Build threat list from validation result"""
    threats = []
    if result.matches:
        for match in result.matches:
            threats.append({
                "severity": match.severity.value if match.severity else "UNKNOWN",
                "rule_name": match.rule_name,
                "description": match.description,
                "context": match.context
            })
    else:
        threats.append({
            "severity": result.severity.value if result.severity else "UNKNOWN",
            "validation_check": result.validation_check,
            "reason": result.reason
        })
    return threats


def _build_status_message(status: str, progress: int, total: int, error: Optional[str]) -> str:
    """Build human-readable status message for scan job"""
    if status == 'pending':
        return "Scan queued, waiting to start"
    if status == 'running':
        pct = int(100 * progress / total) if total > 0 else 0
        return f"Scanning: {progress}/{total} files ({pct}%)"
    if status == 'completed':
        return "Scan complete"
    if status == 'failed':
        return f"Scan failed: {error or 'Unknown error'}"
    return f"Unknown status: {status}"


def _build_scan_response(summary) -> "ScanResponse":
    """Build ScanResponse from scanner summary"""
    return ScanResponse(
        total_files=summary.total_files,
        clean_files=summary.clean_files,
        critical_count=len(summary.critical_findings),
        warning_count=len(summary.warning_findings),
        critical_findings=[_finding_from_summary(f) for f in summary.critical_findings],
        warning_findings=[_finding_from_summary(f) for f in summary.warning_findings],
        auto_quarantine=summary.auto_quarantine,
        message=summary.message
    )


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


def _run_scan_job(job_id: str, auto_quarantine: bool, verbose: bool):
    """Background worker function for security scanning

    Delegates to SecurityScanner class which handles all scanning logic.
    Updates _scan_jobs dict with progress and results.
    """
    try:
        _scan_jobs[job_id]['status'] = 'running'

        kb_path = Path(default_config.paths.knowledge_base)
        db_path = default_config.database.path
        scanner = SecurityScanner(kb_path, db_path)

        def update_progress(count: int):
            _scan_jobs[job_id]['progress'] = count

        # Count files first for progress tracking
        files = scanner.collector.collect()
        _scan_jobs[job_id]['total_files'] = len(files)
        _scan_jobs[job_id]['progress'] = 0

        summary = scanner.scan(job_id, auto_quarantine, update_progress)

        _scan_jobs[job_id]['status'] = 'completed'
        _scan_jobs[job_id]['result'] = _build_scan_response(summary)

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
    error = job.get('error')

    return ScanStatusResponse(
        job_id=job_id,
        status=status,
        progress=progress,
        total_files=total,
        result=job.get('result'),
        error=error,
        message=_build_status_message(status, progress, total, error)
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


@router.post("/scan/file")
async def scan_single_file(file_path: str = Query(..., description="Relative path from knowledge base root")):
    """Scan a specific file for security threats

    Performs immediate security validation on a single file using:
    - ClamAV virus scanning
    - Hash blacklist checking
    - YARA pattern matching
    - File type validation

    This endpoint is synchronous and returns immediate results (no job ID).
    Use this to test individual files or validate uploads before indexing.

    Args:
        file_path: Path relative to knowledge base root (e.g., "books/myfile.pdf")

    Returns:
        Scan result with threat details if found

    Example:
        POST /api/security/scan/file?file_path=books/suspicious.pdf

        Response (clean):
        {
            "file_path": "books/suspicious.pdf",
            "status": "clean",
            "threats_found": 0,
            "scan_time_ms": 45
        }

        Response (threat found):
        {
            "file_path": "books/malware.exe",
            "status": "threat_detected",
            "threats_found": 1,
            "threats": [
                {
                    "severity": "CRITICAL",
                    "validation_check": "ClamAVStrategy",
                    "reason": "Virus detected: Win.Test.EICAR_HDB-1"
                }
            ],
            "scan_time_ms": 52
        }

    Usage:
        # Scan a specific file
        curl -X POST "http://localhost:8000/api/security/scan/file?file_path=test.pdf"

        # URL encode paths with spaces
        curl -X POST "http://localhost:8000/api/security/scan/file?file_path=My%20Book.pdf"
    """
    from time import time
    from ingestion.file_type_validator import FileTypeValidator

    # Resolve full path
    kb_path = default_config.paths.knowledge_base
    full_path = kb_path / file_path

    # Validate file exists
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    if not full_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")

    # Run security validation
    start_time = time()
    validator = FileTypeValidator()
    result = validator.validate(full_path)
    scan_time_ms = int((time() - start_time) * 1000)

    # Build response
    if result.is_valid:
        return {
            "file_path": file_path,
            "file_type": result.file_type,
            "status": "clean",
            "threats_found": 0,
            "scan_time_ms": scan_time_ms
        }

    threats = _build_threats_from_result(result)
    return {
        "file_path": file_path,
        "file_type": result.file_type,
        "status": "threat_detected",
        "threats_found": len(threats),
        "threats": threats,
        "scan_time_ms": scan_time_ms
    }
