# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Tests for security severity tiers (CRITICAL/WARNING/INFO)

Ensures that:
- SecuritySeverity enum has correct values
- ValidationResult correctly determines quarantine/block behavior
- CRITICAL triggers auto-quarantine
- WARNING logs but doesn't auto-quarantine
- INFO is informational only
"""
import pytest
from ingestion.validation_result import (
    SecuritySeverity,
    ValidationResult,
    SecurityMatch,
    ValidationAction
)


class TestSecuritySeverityEnum:
    """Test SecuritySeverity enum values"""

    def test_severity_has_critical(self):
        """SecuritySeverity should have CRITICAL level"""
        assert SecuritySeverity.CRITICAL.value == "critical"

    def test_severity_has_warning(self):
        """SecuritySeverity should have WARNING level"""
        assert SecuritySeverity.WARNING.value == "warning"

    def test_severity_has_info(self):
        """SecuritySeverity should have INFO level"""
        assert SecuritySeverity.INFO.value == "info"

    def test_severity_values_are_lowercase(self):
        """All severity values should be lowercase strings"""
        for severity in SecuritySeverity:
            assert severity.value.islower()
            assert isinstance(severity.value, str)


class TestValidationResultQuarantine:
    """Test ValidationResult.should_quarantine property"""

    def test_critical_should_quarantine(self):
        """CRITICAL severity should trigger quarantine"""
        result = ValidationResult(
            is_valid=False,
            file_type='malware',
            reason='Virus detected',
            validation_check='ClamAVStrategy',
            severity=SecuritySeverity.CRITICAL
        )
        assert result.should_quarantine is True

    def test_warning_should_not_quarantine(self):
        """WARNING severity should NOT trigger quarantine"""
        result = ValidationResult(
            is_valid=False,
            file_type='suspicious',
            reason='YARA match',
            validation_check='YARAStrategy',
            severity=SecuritySeverity.WARNING
        )
        assert result.should_quarantine is False

    def test_info_should_not_quarantine(self):
        """INFO severity should NOT trigger quarantine"""
        result = ValidationResult(
            is_valid=True,
            file_type='pdf',
            reason='Low confidence match',
            validation_check='YARAStrategy',
            severity=SecuritySeverity.INFO
        )
        assert result.should_quarantine is False

    def test_none_severity_should_not_quarantine(self):
        """None severity should NOT trigger quarantine"""
        result = ValidationResult(
            is_valid=False,
            file_type='pdf',
            reason='File too large',
            validation_check='FileSizeStrategy',
            severity=None
        )
        assert result.should_quarantine is False


class TestValidationResultBlock:
    """Test ValidationResult.should_block property"""

    def test_critical_should_block(self):
        """CRITICAL severity should block processing"""
        result = ValidationResult(
            is_valid=False,
            file_type='malware',
            reason='Virus detected',
            validation_check='ClamAVStrategy',
            severity=SecuritySeverity.CRITICAL
        )
        assert result.should_block is True

    def test_warning_should_block(self):
        """WARNING severity should block processing"""
        result = ValidationResult(
            is_valid=False,
            file_type='suspicious',
            reason='YARA match',
            validation_check='YARAStrategy',
            severity=SecuritySeverity.WARNING
        )
        assert result.should_block is True

    def test_info_should_not_block(self):
        """INFO severity should NOT block processing"""
        result = ValidationResult(
            is_valid=True,
            file_type='pdf',
            reason='Low confidence match',
            validation_check='YARAStrategy',
            severity=SecuritySeverity.INFO
        )
        assert result.should_block is False

    def test_none_severity_should_not_block(self):
        """None severity should NOT block processing"""
        result = ValidationResult(
            is_valid=True,
            file_type='pdf',
            reason='',
            validation_check='',
            severity=None
        )
        assert result.should_block is False


class TestSecurityMatch:
    """Test SecurityMatch dataclass"""

    def test_security_match_creation(self):
        """SecurityMatch should store all fields"""
        match = SecurityMatch(
            rule_name='Suspicious_JavaScript',
            severity=SecuritySeverity.WARNING,
            description='JavaScript found in PDF',
            offset=1234,
            context='function evil()'
        )
        assert match.rule_name == 'Suspicious_JavaScript'
        assert match.severity == SecuritySeverity.WARNING
        assert match.description == 'JavaScript found in PDF'
        assert match.offset == 1234
        assert match.context == 'function evil()'

    def test_security_match_defaults(self):
        """SecurityMatch should have sensible defaults"""
        match = SecurityMatch(
            rule_name='Test_Rule',
            severity=SecuritySeverity.INFO
        )
        assert match.description == ""
        assert match.offset is None
        assert match.context == ""


class TestValidationResultWithMatches:
    """Test ValidationResult with SecurityMatch list"""

    def test_result_with_matches(self):
        """ValidationResult should store match details"""
        matches = [
            SecurityMatch(
                rule_name='Rule1',
                severity=SecuritySeverity.WARNING,
                description='Suspicious pattern'
            ),
            SecurityMatch(
                rule_name='Rule2',
                severity=SecuritySeverity.INFO,
                description='Low confidence'
            )
        ]
        result = ValidationResult(
            is_valid=False,
            file_type='suspicious',
            reason='YARA rules matched: Rule1, Rule2',
            validation_check='YARAStrategy',
            severity=SecuritySeverity.WARNING,
            matches=matches
        )
        assert len(result.matches) == 2
        assert result.matches[0].rule_name == 'Rule1'
        assert result.matches[1].rule_name == 'Rule2'

    def test_result_default_empty_matches(self):
        """ValidationResult should default to empty matches list"""
        result = ValidationResult(
            is_valid=True,
            file_type='pdf',
            reason=''
        )
        assert result.matches == []


class TestValidationAction:
    """Test ValidationAction enum"""

    def test_action_has_reject(self):
        """ValidationAction should have REJECT"""
        assert ValidationAction.REJECT.value == "reject"

    def test_action_has_warn(self):
        """ValidationAction should have WARN"""
        assert ValidationAction.WARN.value == "warn"

    def test_action_has_skip(self):
        """ValidationAction should have SKIP"""
        assert ValidationAction.SKIP.value == "skip"


class TestSeverityIntegration:
    """Integration tests for severity-based behavior"""

    def test_clamav_detection_is_critical(self):
        """ClamAV virus detection should be CRITICAL"""
        # Simulate ClamAV result
        result = ValidationResult(
            is_valid=False,
            file_type='malware',
            reason='Virus detected: Win.Test.EICAR',
            validation_check='ClamAVStrategy',
            severity=SecuritySeverity.CRITICAL
        )
        assert result.should_quarantine is True
        assert result.should_block is True

    def test_hash_blacklist_is_critical(self):
        """Hash blacklist match should be CRITICAL"""
        result = ValidationResult(
            is_valid=False,
            file_type='malware',
            reason='Known malware hash',
            validation_check='HashBlacklistStrategy',
            severity=SecuritySeverity.CRITICAL
        )
        assert result.should_quarantine is True
        assert result.should_block is True

    def test_yara_match_is_warning(self):
        """YARA pattern match should be WARNING by default"""
        result = ValidationResult(
            is_valid=False,
            file_type='suspicious',
            reason='YARA rules matched: Suspicious_JavaScript',
            validation_check='YARAStrategy',
            severity=SecuritySeverity.WARNING,
            matches=[
                SecurityMatch(
                    rule_name='Suspicious_JavaScript',
                    severity=SecuritySeverity.WARNING
                )
            ]
        )
        assert result.should_quarantine is False
        assert result.should_block is True

    def test_file_size_validation_no_severity(self):
        """File size validation failures have no severity"""
        result = ValidationResult(
            is_valid=False,
            file_type='pdf',
            reason='File exceeds maximum size (500 MB)',
            validation_check='FileSizeStrategy',
            severity=None
        )
        assert result.should_quarantine is False
        assert result.should_block is False
