"""
Tests for file type validation security feature.

Tests use TDD approach - written before implementation.
"""
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from ingestion.file_type_validator import FileTypeValidator
from ingestion.validation_result import ValidationResult, ValidationAction


class TestFileTypeValidator:
    """Test file type validation logic"""

    def test_valid_pdf_passes_validation(self):
        """Test that valid PDF file passes validation"""
        validator = FileTypeValidator()

        # Create temp file with PDF magic bytes
        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # PDF magic bytes: %PDF-
            f.write(b'%PDF-1.4\n')
            f.write(b'%' + bytes(range(128, 132)))  # PDF header comment
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert result.is_valid
            assert result.file_type == 'pdf'
            assert result.reason == ''
        finally:
            temp_path.unlink()

    def test_valid_docx_passes_validation(self):
        """Test that valid DOCX file (ZIP format) passes validation"""
        import zipfile

        validator = FileTypeValidator()

        # Create temp file with valid DOCX structure (minimal ZIP)
        with NamedTemporaryFile(suffix='.docx', delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Create valid ZIP/DOCX file
            with zipfile.ZipFile(temp_path, 'w') as zf:
                zf.writestr('word/document.xml', '<document/>')

            result = validator.validate(temp_path)
            assert result.is_valid
            assert result.file_type == 'docx'
        finally:
            temp_path.unlink()

    def test_executable_as_pdf_fails_validation(self):
        """Test that executable masquerading as PDF fails validation"""
        validator = FileTypeValidator()

        # Create temp file with ELF executable magic bytes but .pdf extension
        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # ELF magic bytes: 0x7F 'E' 'L' 'F'
            f.write(b'\x7fELF\x02\x01\x01\x00')
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert 'executable' in result.reason.lower() or 'mismatch' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_windows_executable_as_pdf_fails(self):
        """Test that Windows PE executable as PDF fails validation"""
        validator = FileTypeValidator()

        # Create temp file with Windows PE magic bytes
        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # Windows PE: MZ header
            f.write(b'MZ\x90\x00')
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert 'executable' in result.reason.lower() or 'mismatch' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_shell_script_as_pdf_fails(self):
        """Test that shell script as PDF fails validation"""
        validator = FileTypeValidator()

        # Create temp file with shell script shebang
        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'#!/bin/bash\nrm -rf /\n')
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert 'script' in result.reason.lower() or 'mismatch' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_empty_file_fails(self):
        """Test that empty file fails validation"""
        validator = FileTypeValidator()

        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert 'empty' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_markdown_file_passes(self):
        """Test that markdown file passes validation"""
        validator = FileTypeValidator()

        with NamedTemporaryFile(suffix='.md', delete=False) as f:
            f.write(b'# Heading\n\nSome text.')
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert result.is_valid
            assert result.file_type == 'markdown'
        finally:
            temp_path.unlink()

    def test_python_file_passes(self):
        """Test that Python file passes validation"""
        validator = FileTypeValidator()

        with NamedTemporaryFile(suffix='.py', delete=False) as f:
            f.write(b'#!/usr/bin/env python3\nprint("hello")\n')
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert result.is_valid
            assert result.file_type == 'python'
        finally:
            temp_path.unlink()

    def test_unsupported_extension_fails(self):
        """Test that unsupported file extension fails validation"""
        validator = FileTypeValidator()

        with NamedTemporaryFile(suffix='.exe', delete=False) as f:
            f.write(b'MZ\x90\x00')
            temp_path = Path(f.name)

        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert 'unsupported' in result.reason.lower() or 'not allowed' in result.reason.lower()
        finally:
            temp_path.unlink()


class TestValidationAction:
    """Test validation action enum"""

    def test_validation_action_values(self):
        """Test that ValidationAction has expected values"""
        assert hasattr(ValidationAction, 'REJECT')
        assert hasattr(ValidationAction, 'WARN')
        assert hasattr(ValidationAction, 'SKIP')


class TestValidationResult:
    """Test validation result dataclass"""

    def test_validation_result_creation(self):
        """Test creating validation results"""
        result = ValidationResult(
            is_valid=True,
            file_type='pdf',
            reason=''
        )
        assert result.is_valid
        assert result.file_type == 'pdf'
        assert result.reason == ''

    def test_invalid_result_has_reason(self):
        """Test that invalid result includes reason"""
        result = ValidationResult(
            is_valid=False,
            file_type='unknown',
            reason='File type mismatch: expected PDF, got executable'
        )
        assert not result.is_valid
        assert result.reason != ''
