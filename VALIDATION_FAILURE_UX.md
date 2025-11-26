# Validation Failure Handling - Current State & Design Recommendations

**Status:** Design Discussion
**Version:** v1.2.0
**Date:** 2025-11-26

## Current Behavior

### What Happens When Files Fail Validation?

When a file fails security validation (v1.1.0 + v1.2.0 checks), the current behavior is:

```python
# api/ingestion/processing.py:183-193
def _handle_validation_failure(self, doc_file: DocumentFile, validation_result) -> bool:
    if self.validation_action == 'reject':
        print(f"REJECTED (security): {doc_file.name} - {validation_result.reason}")
        return False  # ← File is skipped, no further processing
    elif self.validation_action == 'warn':
        print(f"WARNING (security): {doc_file.name} - {validation_result.reason}")
        return True  # ← File continues to processing (DANGEROUS!)
    elif self.validation_action == 'skip':
        return False  # ← File is skipped silently
```

**Current config** ([config.py:85-88](api/config.py)):
```python
@dataclass
class FileValidationConfig:
    enabled: bool = True
    action: str = "warn"  # Default: WARN (allows malicious files through!)
```

### What Validation Checks Are Performed?

**v1.1.0 - PDF Integrity:**
- Empty files (0 bytes)
- Missing PDF header
- Truncated files (no %%EOF)
- Corrupt xref tables
- Unreadable page structures

**v1.2.0 - Anti-Malware Security:**
- File size bombs (> 500 MB)
- Archive bombs (zip bombs, > 100:1 compression ratio)
- Executables masquerading as documents (.exe → .pdf)
- Scripts with executable permissions (+x bit + shebang)
- Extension mismatches (PDF magic bytes but .txt extension)

### What Happens to Failed Files?

**Current State:**
1. **Console log only** - `print(f"REJECTED (security): {file} - {reason}")`
2. **No database tracking** - Failed files are NOT tracked in `processing_progress`
3. **No quarantine** - Files remain in original location
4. **No notification** - User doesn't know unless watching logs
5. **Lost on restart** - No persistent record of rejection

**Problems:**
- ❌ No audit trail of rejected files
- ❌ Can't review what was blocked
- ❌ Can't whitelist false positives
- ❌ Malicious files stay in knowledge_base/ directory
- ❌ User unaware of security issues

---

## Design Recommendations

### Option A: Track Rejections in Database (Minimal)

**Add `rejected` status to `processing_progress` table:**

```sql
-- New status value
UPDATE processing_progress
SET status = 'rejected', error_message = 'Security validation failed: {reason}'
WHERE file_path = ?
```

**Pros:**
- ✅ Audit trail of all rejected files
- ✅ Visible in completeness API
- ✅ Can query rejected files
- ✅ Minimal code changes

**Cons:**
- ⚠️ Files remain in knowledge_base/
- ⚠️ No way to whitelist false positives
- ⚠️ No separation from processing failures

**Implementation:**
```python
# In processing.py
def _handle_validation_failure(self, doc_file: DocumentFile, validation_result) -> bool:
    if self.validation_action == 'reject':
        print(f"REJECTED (security): {doc_file.name} - {validation_result.reason}")
        if self.tracker:
            self.tracker.mark_rejected(str(doc_file.path), validation_result.reason)
        return False
```

---

### Option B: Quarantine Directory (Production-Ready)

**Move rejected files to `.quarantine/` subdirectory:**

```
knowledge_base/
├── books/
│   └── document.pdf
├── .quarantine/
│   ├── malware.pdf.REJECTED          # Executable as PDF
│   ├── bomb.zip.REJECTED              # Zip bomb
│   └── .metadata.json                 # Rejection details
```

**Quarantine Metadata** (`.quarantine/.metadata.json`):
```json
{
  "malware.pdf": {
    "original_path": "/app/knowledge_base/books/malware.pdf",
    "rejected_at": "2025-11-26T10:30:00Z",
    "reason": "Executable masquerading as pdf (extension mismatch)",
    "validation_check": "ExtensionMismatchStrategy",
    "file_hash": "sha256:abc123...",
    "can_whitelist": true
  }
}
```

**Pros:**
- ✅ Malicious files isolated from knowledge base
- ✅ Can review quarantined files safely
- ✅ Metadata includes whitelist option
- ✅ Clear separation of concerns
- ✅ User can manually restore false positives

**Cons:**
- ⚠️ More complex implementation
- ⚠️ Need quarantine management CLI
- ⚠️ Disk space for quarantined files

**Implementation:**
```python
class QuarantineManager:
    """Manages quarantined files"""

    def quarantine_file(self, file_path: Path, reason: str, check_name: str):
        """Move file to quarantine directory"""
        quarantine_dir = file_path.parent / '.quarantine'
        quarantine_dir.mkdir(exist_ok=True)

        quarantined_name = f"{file_path.name}.REJECTED"
        quarantine_path = quarantine_dir / quarantined_name

        # Move file
        file_path.rename(quarantine_path)

        # Record metadata
        self._write_metadata(quarantine_path, file_path, reason, check_name)

    def restore_file(self, quarantined_file: str):
        """Restore false positive from quarantine"""
        # Move back to original location
        # Add to whitelist
```

**CLI Commands:**
```bash
# List quarantined files
docker-compose exec rag-api python manage.py quarantine list

# Restore false positive
docker-compose exec rag-api python manage.py quarantine restore malware.pdf

# Whitelist specific file (bypass validation)
docker-compose exec rag-api python manage.py quarantine whitelist malware.pdf

# Purge quarantine (delete all)
docker-compose exec rag-api python manage.py quarantine purge --older-than 30d
```

---

### Option C: Hybrid Approach (Recommended)

**Combine database tracking + selective quarantine:**

**Rules:**
1. **Track ALL rejections** in database (Option A)
2. **Quarantine ONLY dangerous files:**
   - Executables masquerading as documents
   - Archive bombs
   - Files with executable permissions + shebang
3. **Leave in place (but track) for:**
   - Empty files (common in code repos)
   - PDF integrity failures (may be partially downloaded)
   - File size warnings (not malicious, just large)

**Why This Works:**
- ✅ Audit trail for everything
- ✅ Dangerous files isolated
- ✅ Empty files (like `__init__.py`) not moved
- ✅ Partially downloaded PDFs can be re-indexed when fixed
- ✅ Balances security vs usability

**Configuration:**
```python
@dataclass
class FileValidationConfig:
    enabled: bool = True
    action: str = "reject"  # ← Change default to reject
    quarantine_dangerous: bool = True  # ← NEW
    quarantine_path: str = ".quarantine"  # ← NEW
```

**Quarantine Decision Logic:**
```python
# Security strategies that should quarantine
QUARANTINE_CHECKS = {
    'ExtensionMismatchStrategy',      # Executables as documents
    'ArchiveBombStrategy',            # Zip bombs
    'ExecutablePermissionStrategy',   # Scripts with +x
}

# Security strategies that should NOT quarantine
TRACK_ONLY_CHECKS = {
    'FileSizeStrategy',               # Just large files, not malicious
    'FileExistenceStrategy',          # Empty files (normal in code repos)
    'PDFIntegrityStrategy',           # Partial downloads, can be fixed
}
```

---

## Special Cases

### Empty Files (`__init__.py`, `README.md`)

**Problem:** Code repositories often have empty `__init__.py` files that are intentionally blank.

**Current Behavior:** FileExistenceStrategy rejects empty files

**Recommendation:**
- Don't quarantine empty files
- Track in database as `rejected` with reason "Empty file (0 bytes)"
- Allow whitelist for specific filenames (`__init__.py`, `.gitkeep`)

**Whitelist Config:**
```python
EMPTY_FILE_WHITELIST = {'__init__.py', '__init__.pyi', '.gitkeep', '.keep'}
```

### PDF Integrity Failures

**Problem:** PDFs might fail integrity check due to:
- Partial downloads (resumable with `curl -C -`)
- In-progress file transfers
- Temporary network issues

**Recommendation:**
- Don't quarantine (not malicious, just incomplete)
- Track in database with `rejected` status
- Mark as `can_retry: true` in metadata
- Retry on next file watcher event (when file changes)

### Large Files (> 500 MB)

**Problem:** Legitimate research papers, books, or datasets might exceed 500 MB.

**Recommendation:**
- Don't quarantine (not malicious, just large)
- Warn user, but allow manual override
- Add to whitelist: `manage.py whitelist add large-dataset.pdf`

---

## Implementation Priority

### Phase 1: Database Tracking (v1.3.0) - NEXT
1. Add `mark_rejected()` to ProcessingProgressTracker
2. Update completeness API to show rejected files
3. Add CLI: `manage.py list-rejected`
4. Change default action from `warn` → `reject`

**Estimated Effort:** 1-2 hours

### Phase 2: Quarantine System (v1.4.0)
1. Implement QuarantineManager
2. Add `.quarantine/` directory support
3. Add metadata tracking
4. Implement whitelist system
5. Add CLI: `quarantine list|restore|whitelist|purge`

**Estimated Effort:** 3-4 hours

### Phase 3: Smart Quarantine Rules (v1.5.0)
1. Separate dangerous checks from non-dangerous
2. Implement selective quarantine
3. Add retry logic for integrity failures
4. Add empty file whitelist

**Estimated Effort:** 2-3 hours

---

## Migration Path

**For existing users with `action: "warn"` config:**

1. Announce breaking change in v1.3.0 release notes
2. Change default from `warn` → `reject`
3. Add migration notice:
   ```
   ⚠️  BREAKING CHANGE: File validation now rejects by default

   Previous behavior (v1.2.0):
     - Files failing validation were WARNED but still indexed (UNSAFE!)

   New behavior (v1.3.0):
     - Files failing validation are REJECTED and tracked in database
     - To restore old behavior: Set FILE_VALIDATION_ACTION=warn

   To review rejected files:
     docker-compose exec rag-api python manage.py list-rejected
   ```

4. Provide opt-out for conservative users:
   ```bash
   # docker-compose.yml
   environment:
     FILE_VALIDATION_ACTION: warn  # Restore v1.2.0 behavior
   ```

---

## Questions for User

1. **Do you want Phase 1 (database tracking) implemented now?**
   - Adds `rejected` status to processing_progress
   - Shows rejected files in completeness API
   - Changes default action to `reject`

2. **Should empty files be whitelisted by default?**
   - Files like `__init__.py`, `.gitkeep` are common in code repos
   - Alternative: Require explicit whitelist

3. **Should we implement quarantine (Phase 2) or just track in DB?**
   - Quarantine is safer but more complex
   - Database-only is simpler but leaves malicious files in place

4. **Default action: `reject` or `warn`?**
   - `reject`: Safer, but might block legitimate files
   - `warn`: Less safe, but more permissive (current default)
