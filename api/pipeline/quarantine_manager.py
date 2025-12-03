"""Quarantine manager for rejected files

Manages quarantine directory for files that fail security validation.
Following hybrid approach: only quarantine dangerous files, track all rejections.

Design decisions:
- Dangerous files (executables, zip bombs, scripts): Moved to quarantine
- Non-dangerous rejections (empty, large, integrity): Tracked but left in place
- Metadata stored in .quarantine/.metadata.json
"""
from pathlib import Path
from typing import Dict, Optional, List
import json
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


# Validation checks that should trigger quarantine (dangerous)
# These are CRITICAL severity - confirmed malware or high-risk files
QUARANTINE_CHECKS = {
    'ExtensionMismatchStrategy',      # Executables as documents
    'ArchiveBombStrategy',            # Zip bombs
    'ExecutablePermissionStrategy',   # Shebang scripts only (non-shebang +x is auto-remediated)
    'ClamAVStrategy',                 # Confirmed virus detection
    'HashBlacklistStrategy',          # Known malware hash
}

# Validation checks that should NOT quarantine (non-dangerous)
# These are WARNING or INFO severity - user should review
TRACK_ONLY_CHECKS = {
    'FileSizeStrategy',               # Just large files, not malicious
    'FileExistenceStrategy',          # Empty files (normal in code repos)
    'PDFIntegrityStrategy',           # Partial downloads, can be fixed
    'YARAStrategy',                   # Pattern matches - often false positives
}


@dataclass
class QuarantineMetadata:
    """Metadata for quarantined file"""
    original_path: str
    quarantined_at: str
    reason: str
    validation_check: str
    file_hash: str = ""
    can_restore: bool = True
    restored: bool = False
    restored_at: Optional[str] = None


class QuarantineManager:
    """Manages quarantine directory for rejected files

    Hybrid approach:
    - Dangerous files → Moved to .quarantine/
    - Non-dangerous → Tracked in DB but left in place

    Directory structure:
        knowledge_base/
        ├── books/
        │   └── document.pdf
        ├── .quarantine/
        │   ├── malware.pdf.REJECTED
        │   ├── bomb.zip.REJECTED
        │   └── .metadata.json
    """

    METADATA_FILE = ".metadata.json"

    def __init__(self, knowledge_base_path: Path):
        """Initialize quarantine manager

        Args:
            knowledge_base_path: Root knowledge base directory
        """
        self.kb_path = knowledge_base_path
        self.quarantine_dir = knowledge_base_path / ".quarantine"

    def should_quarantine(self, validation_check: str) -> bool:
        """Determine if file should be quarantined based on validation check

        Args:
            validation_check: Strategy name that rejected the file

        Returns:
            True if file should be moved to quarantine, False if just tracked
        """
        return validation_check in QUARANTINE_CHECKS

    def quarantine_file(self, file_path: Path, reason: str,
                       validation_check: str, file_hash: str = "") -> bool:
        """Move file to quarantine directory

        Args:
            file_path: Original file path
            reason: Rejection reason
            validation_check: Strategy that rejected it
            file_hash: Optional file hash

        Returns:
            True if quarantined, False if skipped or failed
        """
        # Only quarantine dangerous files
        if not self.should_quarantine(validation_check):
            return False

        # Check file exists
        if not file_path.exists():
            print(f"  ⚠️  Cannot quarantine {file_path.name}: File not found")
            return False

        # Create quarantine directory
        self.quarantine_dir.mkdir(exist_ok=True, parents=True)

        # Generate quarantined filename
        quarantined_name = f"{file_path.name}.REJECTED"
        quarantine_path = self.quarantine_dir / quarantined_name

        # Handle name conflicts
        counter = 1
        while quarantine_path.exists():
            quarantined_name = f"{file_path.name}.REJECTED.{counter}"
            quarantine_path = self.quarantine_dir / quarantined_name
            counter += 1

        try:
            # Move file to quarantine
            shutil.move(str(file_path), str(quarantine_path))

            # Record metadata
            metadata = QuarantineMetadata(
                original_path=str(file_path),
                quarantined_at=datetime.now(timezone.utc).isoformat(),
                reason=reason,
                validation_check=validation_check,
                file_hash=file_hash,
                can_restore=True,
                restored=False
            )
            self._write_metadata(quarantined_name, metadata)

            print(f"  🔒 Quarantined: {file_path.name} → {quarantine_path}")
            return True

        except Exception as e:
            print(f"  ❌ Failed to quarantine {file_path.name}: {e}")
            return False

    def restore_file(self, quarantined_filename: str, force: bool = False) -> bool:
        """Restore file from quarantine to original location"""
        quarantine_path = self.quarantine_dir / quarantined_filename

        error = self._validate_restore(quarantine_path, quarantined_filename, force)
        if error:
            print(error)
            return False

        return self._execute_restore(quarantine_path, quarantined_filename)

    def _validate_restore(self, quarantine_path: Path, filename: str, force: bool) -> str | None:
        """Validate restore is possible, returns error message or None"""
        if not quarantine_path.exists():
            return f"  ❌ File not found in quarantine: {filename}"

        metadata = self._read_metadata(filename)
        if not metadata:
            return f"  ❌ No metadata found for {filename}"

        if metadata.restored:
            return f"  ⚠️  File already restored at {metadata.restored_at}"

        original_path = Path(metadata.original_path)
        if original_path.exists() and not force:
            return f"  ❌ Original path already exists: {original_path}\n     Use --force to overwrite"

        return None

    def _execute_restore(self, quarantine_path: Path, filename: str) -> bool:
        """Execute the restore operation"""
        metadata = self._read_metadata(filename)
        original_path = Path(metadata.original_path)

        try:
            original_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(quarantine_path), str(original_path))

            metadata.restored = True
            metadata.restored_at = datetime.now(timezone.utc).isoformat()
            self._write_metadata(filename, metadata)

            print(f"  ✅ Restored: {filename} → {original_path}")
            return True
        except Exception as e:
            print(f"  ❌ Failed to restore {filename}: {e}")
            return False

    def list_quarantined(self) -> List[QuarantineMetadata]:
        """List all quarantined files

        Returns:
            List of quarantined file metadata
        """
        if not self.quarantine_dir.exists():
            return []

        all_metadata = self._load_all_metadata()
        return [m for m in all_metadata.values() if not m.restored]

    def purge_old_files(self, older_than_days: int, dry_run: bool = False) -> int:
        """Delete quarantined files older than specified days"""
        if not self.quarantine_dir.exists():
            return 0

        cutoff = datetime.now(timezone.utc).timestamp() - (older_than_days * 86400)
        candidates = self._find_purgeable_files(cutoff)

        for filename, metadata in candidates:
            self._purge_file(filename, metadata, dry_run)

        return len(candidates)

    def _find_purgeable_files(self, cutoff_timestamp: float) -> list:
        """Find non-restored files older than cutoff"""
        all_metadata = self._load_all_metadata()
        candidates = []
        for filename, metadata in all_metadata.items():
            if metadata.restored:
                continue
            quarantined_time = datetime.fromisoformat(metadata.quarantined_at).timestamp()
            if quarantined_time < cutoff_timestamp:
                candidates.append((filename, metadata))
        return candidates

    def _purge_file(self, filename: str, metadata: 'QuarantineMetadata', dry_run: bool) -> None:
        """Purge a single file or print dry-run message"""
        if dry_run:
            print(f"  Would purge: {filename} (quarantined {metadata.quarantined_at})")
            return

        quarantine_path = self.quarantine_dir / filename
        if quarantine_path.exists():
            quarantine_path.unlink()
            print(f"  🗑️  Purged: {filename}")

    def _write_metadata(self, quarantined_filename: str, metadata: QuarantineMetadata):
        """Write metadata for quarantined file

        Args:
            quarantined_filename: Name of quarantined file
            metadata: Metadata to write
        """
        metadata_path = self.quarantine_dir / self.METADATA_FILE

        # Load existing metadata
        all_metadata = self._load_all_metadata()

        # Update with new/updated metadata
        all_metadata[quarantined_filename] = metadata

        # Write back
        with open(metadata_path, 'w') as f:
            # Convert dataclasses to dicts for JSON serialization
            serializable = {
                filename: asdict(meta)
                for filename, meta in all_metadata.items()
            }
            json.dump(serializable, f, indent=2)

    def _read_metadata(self, quarantined_filename: str) -> Optional[QuarantineMetadata]:
        """Read metadata for specific quarantined file

        Args:
            quarantined_filename: Name of quarantined file

        Returns:
            QuarantineMetadata or None if not found
        """
        all_metadata = self._load_all_metadata()
        return all_metadata.get(quarantined_filename)

    def _load_all_metadata(self) -> Dict[str, QuarantineMetadata]:
        """Load all quarantine metadata from JSON file

        Returns:
            Dict mapping quarantined filename to metadata
        """
        metadata_path = self.quarantine_dir / self.METADATA_FILE

        if not metadata_path.exists():
            return {}

        try:
            with open(metadata_path, 'r') as f:
                data = json.load(f)
                # Convert dicts back to dataclasses
                return {
                    filename: QuarantineMetadata(**meta_dict)
                    for filename, meta_dict in data.items()
                }
        except Exception as e:
            print(f"  ⚠️  Failed to load quarantine metadata: {e}")
            return {}
