"""
Security validation strategies for anti-malware protection

Following Strategy pattern for composable security checks.
Prevents indexing of malicious, suspicious, or problematic files.

Security Concerns Addressed:
- File size bombs (extremely large files)
- Archive bombs (compression bombs, zip bombs)
- Executable files masquerading as documents
- Suspicious file extension mismatches
- Files with executable permissions

Principles:
- Strategy Pattern for composable checks
- Single Responsibility per strategy
- Tell, Don't Ask principle
"""
from pathlib import Path
from typing import Optional
import os
import zipfile
import tarfile

from ingestion.validation_result import ValidationResult


class FileSizeStrategy:
    """Validates file size is within acceptable limits

    Prevents processing of file size bombs that could:
    - Exhaust disk space
    - Cause out-of-memory errors
    - Slow down the entire system
    """

    # Default limits (can be overridden)
    DEFAULT_MAX_SIZE_MB = 500  # 500 MB max per file
    DEFAULT_WARN_SIZE_MB = 100  # Warn at 100 MB

    def __init__(self, max_size_mb: int = DEFAULT_MAX_SIZE_MB,
                 warn_size_mb: int = DEFAULT_WARN_SIZE_MB):
        """Initialize with size limits

        Args:
            max_size_mb: Maximum file size in MB (hard limit)
            warn_size_mb: Warning threshold in MB (soft limit)
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.warn_size_bytes = warn_size_mb * 1024 * 1024

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check file size is within limits

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type

        Returns:
            ValidationResult with is_valid=False if file exceeds limits
        """
        try:
            file_size = file_path.stat().st_size
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Cannot read file size: {e}'
            )

        # Hard limit - reject
        if file_size > self.max_size_bytes:
            size_mb = file_size / (1024 * 1024)
            max_mb = self.max_size_bytes / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                file_type=expected_type,
                reason=f'File too large: {size_mb:.1f} MB (max: {max_mb:.0f} MB)',
                validation_check='FileSizeStrategy'
            )

        # Soft limit - warn but allow
        if file_size > self.warn_size_bytes:
            size_mb = file_size / (1024 * 1024)
            print(f"  [WARNING] Large file warning: {file_path.name} ({size_mb:.1f} MB)")

        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )


class ArchiveBombStrategy:
    """Detects archive bombs (zip bombs, compression bombs)

    Archive bombs are malicious archives with:
    - Extremely high compression ratios (e.g., 42.zip)
    - Deeply nested archives
    - Massive uncompressed sizes from small compressed files

    Protection against:
    - Disk space exhaustion
    - CPU exhaustion during decompression
    - Memory exhaustion
    """

    # Safety thresholds
    MAX_COMPRESSION_RATIO = 100  # 100:1 compression is suspicious
    MAX_UNCOMPRESSED_SIZE_MB = 1000  # 1 GB uncompressed max
    MAX_NESTING_DEPTH = 2  # Max 2 levels of nested archives

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check for archive bomb characteristics

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type

        Returns:
            ValidationResult with is_valid=False if archive appears malicious
        """
        # Only check archive types
        if not self._is_archive_type(file_path, expected_type):
            return ValidationResult(
                is_valid=True,
                file_type=expected_type,
                reason=''
            )

        # Check compression ratio for zip-based formats
        if self._is_zip_based(file_path):
            return self._check_zip_bomb(file_path, expected_type)

        # Check tar-based formats
        if self._is_tar_based(file_path):
            return self._check_tar_bomb(file_path, expected_type)

        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )

    def _is_archive_type(self, file_path: Path, expected_type: str) -> bool:
        """Check if file is an archive type"""
        archive_extensions = {'.zip', '.epub', '.docx', '.tar', '.gz', '.bz2', '.xz'}
        archive_types = {'epub', 'docx'}

        return (file_path.suffix.lower() in archive_extensions or
                expected_type in archive_types)

    def _is_zip_based(self, file_path: Path) -> bool:
        """Check if file is ZIP-based (ZIP, EPUB, DOCX)"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                return header == b'PK\x03\x04'
        except:
            return False

    def _is_tar_based(self, file_path: Path) -> bool:
        """Check if file is TAR-based"""
        return file_path.suffix.lower() in {'.tar', '.gz', '.bz2', '.xz'}

    def _check_zip_bomb(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check ZIP file for bomb characteristics"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                compressed_size = file_path.stat().st_size
                uncompressed_size = sum(info.file_size for info in zf.infolist())

                result = self._check_archive_sizes(
                    compressed_size, uncompressed_size, expected_type
                )
                if not result.is_valid:
                    return result

                return self._check_nested_archives(zf.namelist(), expected_type)

        except zipfile.BadZipFile:
            return self._corrupted_archive_result('ZIP')
        except Exception:
            pass

        return ValidationResult(is_valid=True, file_type=expected_type, reason='')

    def _check_archive_sizes(
        self, compressed_size: int, uncompressed_size: int, expected_type: str
    ) -> ValidationResult:
        """Check uncompressed size limit and compression ratio"""
        max_size_bytes = self.MAX_UNCOMPRESSED_SIZE_MB * 1024 * 1024
        if uncompressed_size > max_size_bytes:
            return ValidationResult(
                is_valid=False,
                file_type=expected_type,
                reason=f'Archive bomb: Uncompressed size {uncompressed_size // (1024*1024)} MB exceeds limit',
                validation_check='ArchiveBombStrategy'
            )

        if compressed_size > 0:
            ratio = uncompressed_size / compressed_size
            if ratio > self.MAX_COMPRESSION_RATIO:
                return ValidationResult(
                    is_valid=False,
                    file_type=expected_type,
                    reason=f'Archive bomb: Compression ratio {ratio:.0f}:1 is suspicious',
                    validation_check='ArchiveBombStrategy'
                )

        return ValidationResult(is_valid=True, file_type=expected_type, reason='')

    def _check_nested_archives(self, namelist: list, expected_type: str) -> ValidationResult:
        """Check for excessive nested archives"""
        nested_count = sum(
            1 for name in namelist if name.lower().endswith(('.zip', '.tar', '.gz'))
        )
        if nested_count > self.MAX_NESTING_DEPTH:
            return ValidationResult(
                is_valid=False,
                file_type=expected_type,
                reason=f'Archive bomb: Contains {nested_count} nested archives',
                validation_check='ArchiveBombStrategy'
            )
        return ValidationResult(is_valid=True, file_type=expected_type, reason='')

    def _corrupted_archive_result(self, archive_type: str) -> ValidationResult:
        """Return validation result for corrupted archive"""
        return ValidationResult(
            is_valid=False,
            file_type='unknown',
            reason=f'Corrupted {archive_type} archive',
            validation_check='ArchiveBombStrategy'
        )

    def _check_tar_bomb(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check TAR file for bomb characteristics"""
        try:
            with tarfile.open(file_path, 'r:*') as tf:
                uncompressed_size = sum(member.size for member in tf.getmembers())
                compressed_size = file_path.stat().st_size

                return self._check_archive_sizes(
                    compressed_size, uncompressed_size, expected_type
                )

        except (tarfile.TarError, EOFError):
            return self._corrupted_archive_result('TAR')
        except Exception:
            pass

        return ValidationResult(is_valid=True, file_type=expected_type, reason='')


class ExtensionMismatchStrategy:
    """Detects suspicious file extension mismatches

    Identifies files where:
    - Extension doesn't match actual file type (e.g., .exe renamed to .pdf)
    - Magic bytes indicate different format than extension claims

    Common attack vector: malware.exe renamed to document.pdf
    """

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check for extension/content mismatch

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type based on extension

        Returns:
            ValidationResult with is_valid=False if mismatch detected
        """
        # Read magic bytes
        try:
            with open(file_path, 'rb') as f:
                header = f.read(512)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Cannot read file: {e}'
            )

        # Check for executable masquerading as document
        if expected_type in {'pdf', 'docx', 'epub', 'markdown', 'text'}:
            actual_type = self._detect_actual_type(header)

            if actual_type == 'executable':
                return ValidationResult(
                    is_valid=False,
                    file_type='executable',
                    reason=f'Executable masquerading as {expected_type} (extension mismatch)',
                    validation_check='ExtensionMismatchStrategy'
                )

            # Check for specific mismatches
            if actual_type and actual_type != expected_type:
                # Allow some known compatible formats
                if not self._is_compatible_format(expected_type, actual_type):
                    return ValidationResult(
                        is_valid=False,
                        file_type=actual_type,
                        reason=f'Extension claims {expected_type} but file is {actual_type}',
                        validation_check='ExtensionMismatchStrategy'
                    )

        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )

    def _detect_actual_type(self, header: bytes) -> Optional[str]:
        """Detect actual file type from magic bytes"""
        # Executable signatures
        if header.startswith(b'\x7fELF'):
            return 'executable'
        if header.startswith(b'MZ'):
            return 'executable'
        if header.startswith(b'\xca\xfe\xba\xbe'):
            return 'executable'
        if header.startswith(b'\xfe\xed\xfa'):
            return 'executable'

        # Document signatures
        if header.startswith(b'%PDF-'):
            return 'pdf'
        if header.startswith(b'PK\x03\x04'):
            return 'zip_based'  # Could be DOCX, EPUB, or ZIP

        return None

    def _is_compatible_format(self, expected: str, actual: str) -> bool:
        """Check if formats are compatible (not a mismatch)"""
        # DOCX and EPUB are both ZIP-based, so zip_based is compatible
        if actual == 'zip_based' and expected in {'docx', 'epub'}:
            return True

        return False


class ExecutablePermissionStrategy:
    """Detects files with executable permissions

    Files with execute permissions are suspicious in a document repository.
    Returns is_valid=False for ANY file with +x, allowing PipelineCoordinator
    to attempt remediation (remove +x) before final rejection.

    Shebang scripts (#!/bin/...) are distinguished via file_type='script'
    so coordinator can reject them without remediation attempt.
    """

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check if file has executable permissions

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type

        Returns:
            ValidationResult with is_valid=False if file has any execute bit
        """
        try:
            mode = file_path.stat().st_mode
            is_executable = bool(mode & 0o111)

            if is_executable:
                has_shebang = self._has_shebang(file_path)
                if has_shebang:
                    return ValidationResult(
                        is_valid=False,
                        file_type='script',
                        reason=f'Script with executable permissions (shebang detected)',
                        validation_check='ExecutablePermissionStrategy'
                    )
                else:
                    return ValidationResult(
                        is_valid=False,
                        file_type=expected_type,
                        reason='Executable permission detected',
                        validation_check='ExecutablePermissionStrategy'
                    )

        except Exception:
            # If we can't check permissions, let it through
            pass

        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )

    def _has_shebang(self, file_path: Path) -> bool:
        """Check if file starts with shebang (#!)"""
        try:
            with open(file_path, 'rb') as f:
                return f.read(2) == b'#!'
        except Exception:
            return False
