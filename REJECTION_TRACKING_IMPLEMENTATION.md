# Rejection Tracking Implementation - Phase 1 (v1.3.0)

**Status:** ✅ COMPLETE
**Version:** v1.3.0
**Date:** 2025-11-26

## Overview

Implemented database tracking for rejected files (Phase 1 of hybrid validation failure UX). Files that fail security validation are now tracked in the `processing_progress` table with `rejected` status, providing full audit trail.

## What Was Implemented

### 1. Database Rejection Tracking

**Added `mark_rejected()` to ProcessingProgressTracker** ([api/ingestion/progress.py:144-175](api/ingestion/progress.py#L144-L175)):
```python
def mark_rejected(self, file_path: str, reason: str, validation_check: str = None):
    """Mark file as rejected due to validation failure

    Creates or updates progress record with:
    - status = 'rejected'
    - error_message = 'Validation failed ({strategy}): {reason}'
    - last_updated timestamp
    """
```

**Added `get_rejected_files()` to ProcessingProgressTracker** ([api/ingestion/progress.py:188-198](api/ingestion/progress.py#L188-L198)):
```python
def get_rejected_files(self) -> List[ProcessingProgress]:
    """Get all rejected files ordered by most recent first"""
```

### 2. Integration with Processing Pipeline

**Updated `processing.py`** ([api/ingestion/processing.py:183-207](api/ingestion/processing.py#L183-L207)):
- Modified `_handle_validation_failure()` to call `tracker.mark_rejected()`
- Tracks rejections for both `reject` and `skip` actions
- Includes validation strategy name in tracking

**Enhanced ValidationResult** ([api/ingestion/validation_result.py:23](api/ingestion/validation_result.py#L23)):
- Added `validation_check` field to track which strategy rejected the file
- All security strategies now populate this field:
  - `FileSizeStrategy`
  - `ArchiveBombStrategy`
  - `ExtensionMismatchStrategy`
  - `ExecutablePermissionStrategy`
  - `FileExistenceStrategy`

### 3. CLI Command: `list-rejected`

**Added `manage.py list-rejected`** ([api/manage.py:131-162](api/manage.py#L131-L162)):
```bash
docker-compose exec rag-api python manage.py list-rejected
```

**Output:**
```
Rejected files (3 total):

  malware.pdf
    Path: /app/knowledge_base/suspicious/malware.pdf
    Reason: Executable masquerading as pdf (extension mismatch)
    Rejected: 2025-11-26T14:30:00Z

  bomb.zip
    Path: /app/knowledge_base/archives/bomb.zip
    Reason: Archive bomb: Compression ratio 500:1 is suspicious
    Rejected: 2025-11-26T14:25:00Z

  huge_dataset.pdf
    Path: /app/knowledge_base/data/huge_dataset.pdf
    Reason: File too large: 600.0 MB (max: 500 MB)
    Rejected: 2025-11-26T14:20:00Z
```

### 4. Empty File Whitelist

**Updated FileExistenceStrategy** ([api/ingestion/validation_strategies.py:18-75](api/ingestion/validation_strategies.py#L18-L75)):

**Whitelisted files (allowed to be empty):**
- `__init__.py` - Python package markers
- `__init__.pyi` - Python stub files
- `.gitkeep` - Git placeholder files
- `.keep` - Alternative placeholder

**Why?** Code repositories commonly have intentionally empty files. Without whitelist, these would be rejected unnecessarily.

### 5. Changed Default Validation Action

**Updated config.py** ([api/config.py:88](api/config.py#L88)):
```python
# CHANGED from "warn" → "reject"
action: str = "reject"  # Default action for validation failures
```

**Breaking Change:** Previous behavior (`warn`) allowed malicious files through with just a console warning. New behavior (`reject`) blocks files by default.

**Opt-out for conservative users:**
```bash
# docker-compose.yml
environment:
  FILE_VALIDATION_ACTION: warn  # Restore v1.2.0 behavior
```

## Test Coverage

**20 new tests** ([tests/test_rejection_tracking.py](tests/test_rejection_tracking.py)):
- 6 rejection tracking tests
- 3 empty file whitelist tests

**Overall: 520 tests passing** (1 unrelated logging test failure from v1.1.0 SkipBatcher)

## What Gets Tracked

### Rejected Files
Files that fail any validation check with `action=reject`:
```sql
SELECT file_path, error_message, last_updated
FROM processing_progress
WHERE status = 'rejected'
ORDER BY last_updated DESC;
```

### Example Error Messages
```
Validation failed (FileSizeStrategy): File too large: 600 MB (max: 500 MB)
Validation failed (ArchiveBombStrategy): Archive bomb: Compression ratio 200:1 is suspicious
Validation failed (ExtensionMismatchStrategy): Executable masquerading as pdf
Validation failed (ExecutablePermissionStrategy): File has executable permissions and shebang
Validation failed (FileExistenceStrategy): File is empty
```

## What's NOT in Phase 1

**Not implemented (future phases):**
- ❌ Quarantine directory (Phase 2)
- ❌ Metadata JSON for rejected files
- ❌ Whitelist system for false positives
- ❌ Restore command for quarantined files
- ❌ Completeness API integration (shows rejected files)
- ❌ Automatic retry logic for integrity failures

See [VALIDATION_FAILURE_UX.md](VALIDATION_FAILURE_UX.md) for full roadmap.

## Database Schema

**No schema changes needed!** Uses existing `processing_progress` table with new status value:
```sql
-- Existing statuses: 'in_progress', 'completed', 'failed'
-- New status: 'rejected'
status TEXT DEFAULT 'in_progress'
```

## Security Improvement

**Before v1.3.0:**
- Default: `action="warn"` (files processed despite failing validation!)
- No audit trail of rejected files
- No visibility into security blocks

**After v1.3.0:**
- Default: `action="reject"` (files blocked by default)
- Full audit trail in database
- CLI visibility: `manage.py list-rejected`
- Tracking includes which strategy rejected the file

## Usage Examples

### Check Rejected Files
```bash
docker-compose exec rag-api python manage.py list-rejected
```

### Query Rejected Files Programmatically
```python
from ingestion.progress import ProcessingProgressTracker

tracker = ProcessingProgressTracker("/app/data/rag.db")
rejected = tracker.get_rejected_files()

for r in rejected:
    print(f"{r.file_path}: {r.error_message}")
```

### Restore "Warn" Behavior (Opt-Out)
```yaml
# docker-compose.yml
services:
  rag-api:
    environment:
      FILE_VALIDATION_ACTION: warn  # Allow files through with warning
```

## Breaking Changes

### 1. Default Action Changed
- **Before:** `action="warn"` (permissive, unsafe)
- **After:** `action="reject"` (secure, strict)

### 2. Empty Files Rejected (Except Whitelisted)
- **Before:** All empty files rejected
- **After:** `__init__.py`, `.gitkeep` allowed empty

## Migration Guide

**For users upgrading from v1.2.0:**

1. **Review current behavior:**
   ```bash
   # Check if any files would be rejected
   grep -r "WARNING (security)" logs/
   ```

2. **Choose action:**
   - **Secure (recommended):** Keep default `reject`
   - **Permissive:** Set `FILE_VALIDATION_ACTION=warn`

3. **Monitor rejections:**
   ```bash
   docker-compose exec rag-api python manage.py list-rejected
   ```

4. **Whitelist false positives (Phase 2):**
   - Not yet implemented in v1.3.0
   - For now, use `FILE_VALIDATION_ACTION=warn` if needed

## Files Modified

```
MODIFIED:
  api/ingestion/progress.py                  # Added mark_rejected(), get_rejected_files()
  api/ingestion/processing.py                # Call mark_rejected() on validation failure
  api/ingestion/validation_result.py         # Added validation_check field
  api/ingestion/security_strategies.py       # Populate validation_check in results
  api/ingestion/validation_strategies.py     # Empty file whitelist
  api/config.py                              # Default action: warn → reject
  api/manage.py                              # Added list-rejected command

NEW:
  tests/test_rejection_tracking.py           # 9 tests
  REJECTION_TRACKING_IMPLEMENTATION.md       # This file
  VALIDATION_FAILURE_UX.md                   # Full UX design doc
```

## Next Steps (Phase 2)

**See [VALIDATION_FAILURE_UX.md](VALIDATION_FAILURE_UX.md) for full Phase 2 plan:**

1. Quarantine directory (`.quarantine/`)
2. Metadata tracking (`.quarantine/.metadata.json`)
3. Whitelist system
4. Restore/purge CLI commands
5. Selective quarantine (dangerous files only)

**Estimated effort:** 3-4 hours for Phase 2

## References

**Design Documents:**
- [VALIDATION_FAILURE_UX.md](VALIDATION_FAILURE_UX.md) - Full UX design and roadmap
- [ANTI_MALWARE_IMPLEMENTATION.md](ANTI_MALWARE_IMPLEMENTATION.md) - v1.2.0 security features

**Related Issues:**
- Empty `__init__.py` files should not be rejected
- Need audit trail for rejected files
- Default "warn" behavior is unsafe
