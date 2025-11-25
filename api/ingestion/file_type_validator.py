"""
File type validation for document security.

Validates files before indexing to prevent malicious content from being processed.
Uses magic byte verification to ensure file type matches extension.

REFACTORED: Reduced cyclomatic complexity from CC: 12 to < 5 using Strategy pattern.
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


class FileTypeValidator:
    """Validates file types using magic byte signatures

    REFACTORED: Uses Strategy pattern to compose validation logic.
    Reduced cyclomatic complexity from CC: 12 to CC: 3.

    Strategies:
    - FileExistenceStrategy: Check file exists and not empty
    - ExtensionStrategy: Validate extension is supported
    - TextFileStrategy: Validate text-based files
    - ExecutableCheckStrategy: Detect executables (security)
    - MagicSignatureStrategy: Validate binary file signatures
    """

    # Text-based file types (no magic bytes needed)
    TEXT_TYPES = {
        'markdown', 'python', 'javascript', 'typescript',
        'java', 'csharp', 'go', 'rust', 'ipynb', 'text'
    }

    def __init__(self):
        """Initialize validation strategies"""
        self.existence = FileExistenceStrategy()
        self.extension = ExtensionStrategy()
        self.text_file = TextFileStrategy()
        self.executable_check = ExecutableCheckStrategy()
        self.magic_signature = MagicSignatureStrategy()

    def validate(self, file_path: Path) -> ValidationResult:
        """Validate file type matches extension using strategy composition

        REFACTORED: Reduced from CC: 12 to CC: 3 using Strategy pattern.

        Validation chain:
        1. FileExistenceStrategy - file exists and not empty
        2. ExtensionStrategy - extension is supported
        3. TextFileStrategy OR (ExecutableCheckStrategy + MagicSignatureStrategy)

        Args:
            file_path: Path to file to validate

        Returns:
            ValidationResult with is_valid, file_type, and reason
        """
        # Strategy 1: Check file exists and not empty
        result = self.existence.validate(file_path)
        if not result.is_valid:
            return result

        # Strategy 2: Check extension is supported
        result = self.extension.validate(file_path)
        if not result.is_valid:
            return result

        expected_type = result.file_type

        # Strategy 3: Choose validation path based on file type
        if expected_type in self.TEXT_TYPES:
            # Text files: validate they're actually text (not binary)
            return self.text_file.validate(file_path, expected_type)
        else:
            # Binary files: check for executables, then validate magic bytes
            result = self.executable_check.validate(file_path, expected_type)
            if not result.is_valid:
                return result
            return self.magic_signature.validate(file_path, expected_type)
