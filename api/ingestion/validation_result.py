"""
Validation result value objects

Extracted to avoid circular imports between file_type_validator and validation_strategies.
"""
from dataclasses import dataclass
from enum import Enum


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
    validation_check: str = ""  # Strategy that performed the check (e.g., "FileSizeStrategy")
