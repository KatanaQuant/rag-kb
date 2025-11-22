"""
File type validation for document security.

Validates files before indexing to prevent malicious content from being processed.
Uses magic byte verification to ensure file type matches extension.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple


class ValidationAction(Enum):
    """Action to take when validation fails"""
    REJECT = "reject"  # Reject file completely
    WARN = "warn"      # Log warning but process
    SKIP = "skip"      # Skip file silently


@dataclass
class ValidationResult:
    """Result of file type validation"""
    is_valid: bool
    file_type: str
    reason: str = ""


class FileTypeValidator:
    """Validates file types using magic byte signatures"""

    # Magic bytes for supported file types
    # Format: (magic_bytes, offset, description)
    MAGIC_SIGNATURES: Dict[str, List[Tuple[bytes, int, str]]] = {
        'pdf': [
            (b'%PDF-', 0, 'PDF document'),
        ],
        'docx': [
            (b'PK\x03\x04', 0, 'Office Open XML (DOCX/XLSX/PPTX)'),
        ],
        'doc': [
            (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 0, 'Microsoft Office document'),
        ],
        'epub': [
            (b'PK\x03\x04', 0, 'EPUB (ZIP-based)'),
        ],
        'markdown': [],  # Text-based, no magic bytes
        'python': [],    # Text-based, no magic bytes
        'javascript': [],  # Text-based, no magic bytes
        'typescript': [],  # Text-based, no magic bytes
        'java': [],      # Text-based, no magic bytes
        'csharp': [],    # Text-based, no magic bytes
        'go': [],        # Text-based, no magic bytes
        'rust': [],      # Text-based, no magic bytes
        'ipynb': [],     # JSON-based, no magic bytes
    }

    # Executable magic bytes (dangerous)
    EXECUTABLE_SIGNATURES = [
        (b'\x7fELF', 0, 'ELF executable (Linux)'),
        (b'MZ', 0, 'Windows PE executable'),
        (b'\xca\xfe\xba\xbe', 0, 'Mach-O executable (macOS)'),
        (b'\xfe\xed\xfa\xce', 0, 'Mach-O 32-bit executable'),
        (b'\xfe\xed\xfa\xcf', 0, 'Mach-O 64-bit executable'),
        (b'\xce\xfa\xed\xfe', 0, 'Mach-O reverse byte order'),
        (b'#!', 0, 'Shell script'),
    ]

    # File extension to type mapping
    EXTENSION_MAP = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.doc': 'doc',
        '.epub': 'epub',
        '.md': 'markdown',
        '.markdown': 'markdown',
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.ipynb': 'ipynb',
        '.txt': 'text',
    }

    def validate(self, file_path: Path) -> ValidationResult:
        """Validate file type matches extension

        Args:
            file_path: Path to file to validate

        Returns:
            ValidationResult with is_valid, file_type, and reason
        """
        # Check file exists
        if not file_path.exists():
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'File does not exist: {file_path}'
            )

        # Check file is not empty
        if file_path.stat().st_size == 0:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason='File is empty'
            )

        # Get expected type from extension
        extension = file_path.suffix.lower()
        expected_type = self.EXTENSION_MAP.get(extension)

        if expected_type is None:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Unsupported file extension: {extension}'
            )

        # Read first 512 bytes for magic byte check
        try:
            with open(file_path, 'rb') as f:
                header = f.read(512)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Cannot read file: {e}'
            )

        # For text-based files (source code, markdown), validate they're actually text
        # Note: Shebangs (#!) are normal for Python/scripts, so we skip executable checks for text files
        if expected_type in ['markdown', 'python', 'javascript', 'typescript', 'java', 'csharp', 'go', 'rust', 'ipynb', 'text']:
            if not self._is_text_file(header):
                return ValidationResult(
                    is_valid=False,
                    file_type='binary',
                    reason=f'File appears to be binary, expected text-based {expected_type}'
                )
            # Text files pass validation (shebangs are OK for scripts)
            return ValidationResult(
                is_valid=True,
                file_type=expected_type,
                reason=''
            )

        # For binary files (PDF, DOCX, etc.), check for executable signatures (security risk)
        # Executables masquerading as documents are dangerous
        for magic_bytes, offset, description in self.EXECUTABLE_SIGNATURES:
            if self._matches_signature(header, magic_bytes, offset):
                return ValidationResult(
                    is_valid=False,
                    file_type='executable',
                    reason=f'File appears to be an executable ({description}), not {expected_type}'
                )

        # For binary files with magic bytes, verify signature
        signatures = self.MAGIC_SIGNATURES.get(expected_type, [])
        if signatures:
            for magic_bytes, offset, description in signatures:
                if self._matches_signature(header, magic_bytes, offset):
                    return ValidationResult(
                        is_valid=True,
                        file_type=expected_type,
                        reason=''
                    )

            # No matching signature found
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'File signature does not match {expected_type} format'
            )

        # No signatures defined but not text-based (shouldn't happen)
        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )

    def _matches_signature(self, data: bytes, signature: bytes, offset: int) -> bool:
        """Check if data matches signature at given offset"""
        if len(data) < offset + len(signature):
            return False
        return data[offset:offset + len(signature)] == signature

    def _is_text_file(self, data: bytes) -> bool:
        """Check if file appears to be text-based

        Uses heuristic: text files should have mostly printable ASCII/UTF-8 characters
        """
        if len(data) == 0:
            return True

        # Sample first 512 bytes
        sample = data[:512]

        # Count printable characters
        printable = 0
        for byte in sample:
            # Printable ASCII: space (32) to tilde (126), plus common whitespace
            if (32 <= byte <= 126) or byte in [9, 10, 13]:  # tab, newline, carriage return
                printable += 1

        # File is text if >90% printable characters
        ratio = printable / len(sample)
        return ratio > 0.9
