"""
Validation result value objects

Extracted to avoid circular imports between file_type_validator and validation_strategies.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class ValidationAction(Enum):
    """Action to take when validation fails"""
    REJECT = "reject"  # Reject file completely
    WARN = "warn"      # Log warning but process
    SKIP = "skip"      # Skip file silently


class SecuritySeverity(Enum):
    """Security detection severity levels

    Determines automatic actions:
    - CRITICAL: Auto-quarantine + delete from DB
    - WARNING: Log + flag, no auto-action
    - INFO: Log only, informational
    """
    CRITICAL = "critical"  # Confirmed malware (ClamAV, hash blacklist)
    WARNING = "warning"    # Suspicious patterns (YARA heuristics)
    INFO = "info"          # Informational (low-confidence matches)


@dataclass
class SecurityMatch:
    """Details of a security rule match"""
    rule_name: str
    severity: SecuritySeverity
    description: str = ""
    offset: Optional[int] = None  # Byte offset where match occurred
    context: str = ""  # Additional context (e.g., "likely embedded font")


@dataclass
class ValidationResult:
    """Result of file type validation"""
    is_valid: bool
    file_type: str
    reason: str = ""
    validation_check: str = ""  # Strategy that performed the check (e.g., "FileSizeStrategy")
    severity: Optional[SecuritySeverity] = None  # For security detections
    matches: List[SecurityMatch] = field(default_factory=list)  # Detailed match info

    @property
    def should_quarantine(self) -> bool:
        """Whether this result warrants automatic quarantine"""
        return self.severity == SecuritySeverity.CRITICAL

    @property
    def should_block(self) -> bool:
        """Whether this result should block processing"""
        return self.severity in (SecuritySeverity.CRITICAL, SecuritySeverity.WARNING)
