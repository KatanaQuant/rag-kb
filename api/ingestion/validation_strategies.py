"""
Validation strategies for FileTypeValidator refactoring

Following Strategy pattern to reduce cyclomatic complexity from CC: 12 to < 5.
Each strategy handles one specific validation concern.

Benefits:
- Single Responsibility Principle - each strategy has one reason to change
- Open/Closed Principle - can add new strategies without modifying existing code
- Reduced complexity - simple, testable components
- Composable - strategies can be chained together
"""
from pathlib import Path
from typing import Dict, List, Tuple
from ingestion.validation_result import ValidationResult


class FileExistenceStrategy:
    """Validates file exists and is not empty

    First check in validation chain - no point continuing if file doesn't exist.
    """

    def validate(self, file_path: Path) -> ValidationResult:
        """Check file exists and has content

        Args:
            file_path: Path to file to validate

        Returns:
            ValidationResult with is_valid=True if file exists and not empty
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

        return ValidationResult(
            is_valid=True,
            file_type='unknown',
            reason=''
        )


class ExtensionStrategy:
    """Validates file extension is supported

    Maps extensions to expected file types for subsequent validation.
    """

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
        """Check file extension is supported

        Args:
            file_path: Path to file to validate

        Returns:
            ValidationResult with is_valid=True and file_type if extension supported
        """
        extension = file_path.suffix.lower()
        expected_type = self.EXTENSION_MAP.get(extension)

        if expected_type is None:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Unsupported file extension: {extension}'
            )

        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )


class TextFileStrategy:
    """Validates text-based files (source code, markdown)

    Ensures files claiming to be text are actually text, not binary.
    """

    # Text-based file types (no magic bytes needed)
    TEXT_TYPES = {
        'markdown', 'python', 'javascript', 'typescript',
        'java', 'csharp', 'go', 'rust', 'ipynb', 'text'
    }

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Validate text-based file is actually text

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type (e.g., 'python', 'markdown')

        Returns:
            ValidationResult with is_valid=True if file is text-based
        """
        # Read first 512 bytes for text detection
        try:
            with open(file_path, 'rb') as f:
                header = f.read(512)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Cannot read file: {e}'
            )

        # Check if file appears to be text
        if not self._is_text_file(header):
            return ValidationResult(
                is_valid=False,
                file_type='binary',
                reason=f'File appears to be binary, expected text-based {expected_type}'
            )

        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )

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


class ExecutableCheckStrategy:
    """Checks for executable signatures (security)

    Detects executables masquerading as documents - critical security check.
    """

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

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Check file is not an executable

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type (e.g., 'pdf', 'docx')

        Returns:
            ValidationResult with is_valid=False if file is executable
        """
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

        # Check for executable signatures
        for magic_bytes, offset, description in self.EXECUTABLE_SIGNATURES:
            if self._matches_signature(header, magic_bytes, offset):
                return ValidationResult(
                    is_valid=False,
                    file_type='executable',
                    reason=f'File appears to be an executable ({description}), not {expected_type}'
                )

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


class MagicSignatureStrategy:
    """Validates binary file magic bytes

    Ensures binary files (PDF, DOCX) have correct file signatures.
    """

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

    def validate(self, file_path: Path, expected_type: str) -> ValidationResult:
        """Validate file magic bytes match expected type

        Args:
            file_path: Path to file to validate
            expected_type: Expected file type (e.g., 'pdf', 'docx')

        Returns:
            ValidationResult with is_valid=True if signature matches
        """
        header = self._read_file_header(file_path)
        if isinstance(header, ValidationResult):
            return header

        signatures = self.MAGIC_SIGNATURES.get(expected_type, [])

        if self._is_text_based(signatures):
            return self._validation_success(expected_type)

        if self._has_matching_signature(header, signatures):
            return self._validation_success(expected_type)

        return self._validation_failure(expected_type)

    def _read_file_header(self, file_path: Path):
        """Read file header for magic byte check"""
        try:
            with open(file_path, 'rb') as f:
                return f.read(512)
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                file_type='unknown',
                reason=f'Cannot read file: {e}'
            )

    def _is_text_based(self, signatures: List) -> bool:
        """Check if file type has no signatures (text-based)"""
        return not signatures

    def _has_matching_signature(self, header: bytes, signatures: List[Tuple[bytes, int, str]]) -> bool:
        """Check if header matches any signature"""
        for magic_bytes, offset, description in signatures:
            if self._matches_signature(header, magic_bytes, offset):
                return True
        return False

    def _validation_success(self, expected_type: str) -> ValidationResult:
        """Return success validation result"""
        return ValidationResult(
            is_valid=True,
            file_type=expected_type,
            reason=''
        )

    def _validation_failure(self, expected_type: str) -> ValidationResult:
        """Return failure validation result"""
        return ValidationResult(
            is_valid=False,
            file_type='unknown',
            reason=f'File signature does not match {expected_type} format'
        )

    def _matches_signature(self, data: bytes, signature: bytes, offset: int) -> bool:
        """Check if data matches signature at given offset"""
        if len(data) < offset + len(signature):
            return False
        return data[offset:offset + len(signature)] == signature
