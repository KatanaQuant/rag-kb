"""
File type validation for document security.

Validates files before indexing to prevent malicious content from being processed.
Uses magic byte verification to ensure file type matches extension.
"""
from pathlib import Path
from ingestion.validation_result import ValidationResult, ValidationAction
from ingestion.validation_strategies import (
    FileExistenceStrategy,
    ExtensionStrategy,
    TextFileStrategy,
    ExecutableCheckStrategy,
    MagicSignatureStrategy
)
from ingestion.security_strategies import (
    FileSizeStrategy,
    ArchiveBombStrategy,
    ExtensionMismatchStrategy,
    ExecutablePermissionStrategy
)
from ingestion.malware_detection import AdvancedMalwareDetector
from config import default_config


class FileTypeValidator:
    """Validates file types using magic byte signatures.

    Uses Strategy pattern to compose validation logic.

    Validation Strategies:
    - FileExistenceStrategy: Check file exists and not empty
    - ExtensionStrategy: Validate extension is supported
    - TextFileStrategy: Validate text-based files
    - ExecutableCheckStrategy: Detect executables (security)
    - MagicSignatureStrategy: Validate binary file signatures

    Security Strategies:
    - FileSizeStrategy: Prevent file size bombs
    - ArchiveBombStrategy: Detect compression bombs
    - ExtensionMismatchStrategy: Catch executables renamed as documents
    - ExecutablePermissionStrategy: Detect files with exec permissions

    Advanced Malware Detection:
    - ClamAV: Virus signature scanning (optional)
    - Hash Blacklist: Known malware SHA256 database (optional)
    - YARA: Custom pattern matching (optional)
    """

    # Text-based file types (no magic bytes needed)
    TEXT_TYPES = {
        'markdown', 'python', 'javascript', 'typescript',
        'java', 'csharp', 'go', 'rust', 'ipynb', 'text'
    }

    def __init__(self):
        """Initialize validation and security strategies"""
        # Core validation strategies
        self.existence = FileExistenceStrategy()
        self.extension = ExtensionStrategy()
        self.text_file = TextFileStrategy()
        self.executable_check = ExecutableCheckStrategy()
        self.magic_signature = MagicSignatureStrategy()

        # Security strategies
        self.file_size = FileSizeStrategy(max_size_mb=500, warn_size_mb=100)
        self.archive_bomb = ArchiveBombStrategy()
        self.extension_mismatch = ExtensionMismatchStrategy()
        self.exec_permission = ExecutablePermissionStrategy()

        # Advanced malware detection
        self.malware_detector = AdvancedMalwareDetector(default_config.malware_detection)

    def validate(self, file_path: Path) -> ValidationResult:
        """Validate file type matches extension using strategy composition.

        Validation chain:
        1. FileExistenceStrategy - file exists and not empty
        2. FileSizeStrategy - file size within limits
        3. ExtensionStrategy - extension is supported
        4. ExecutablePermissionStrategy - no exec permissions
        5. ExtensionMismatchStrategy - extension matches content
        6. ArchiveBombStrategy - compression ratio safe
        7. AdvancedMalwareDetector - ClamAV/hash/YARA (optional)
        8. TextFileStrategy OR (ExecutableCheckStrategy + MagicSignatureStrategy)

        Args:
            file_path: Path to file to validate

        Returns:
            ValidationResult with is_valid, file_type, and reason
        """
        # Step 1: Check file exists and not empty
        result = self.existence.validate(file_path)
        if not result.is_valid:
            return result

        # Step 2: Security - Check file size limits
        result = self.file_size.validate(file_path, 'unknown')
        if not result.is_valid:
            return result

        # Step 3: Check extension is supported
        result = self.extension.validate(file_path)
        if not result.is_valid:
            return result

        expected_type = result.file_type

        # Step 4: Security - Check executable permissions
        result = self.exec_permission.validate(file_path, expected_type)
        if not result.is_valid:
            return result

        # Step 5: Security - Check extension/content mismatch
        result = self.extension_mismatch.validate(file_path, expected_type)
        if not result.is_valid:
            return result

        # Step 6: Security - Check for archive bombs
        result = self.archive_bomb.validate(file_path, expected_type)
        if not result.is_valid:
            return result

        # Step 7: Advanced malware detection
        result = self.malware_detector.validate(file_path, expected_type)
        if not result.is_valid:
            return result

        # Step 8: Type-specific validation
        if expected_type in self.TEXT_TYPES:
            # Text files: validate they're actually text (not binary)
            return self.text_file.validate(file_path, expected_type)
        else:
            # Binary files: check for executables, then validate magic bytes
            result = self.executable_check.validate(file_path, expected_type)
            if not result.is_valid:
                return result
            return self.magic_signature.validate(file_path, expected_type)
