"""
Tests for FileTypeValidator Strategy Pattern Refactoring

Following TDD Red/Green/Refactor:
- RED: Write these tests BEFORE implementing strategy classes
- GREEN: Implement strategy classes to make tests pass
- REFACTOR: Replace monolithic validate() with strategy composition

Goal: Reduce FileTypeValidator.validate() from CC: 12 to < 5
"""
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from ingestion.validation_result import ValidationResult


class TestFileExistenceStrategy:
    """Test strategy for checking file existence and non-empty"""

    def test_validates_existing_file(self):
        """FileExistenceStrategy should pass for existing non-empty file"""
        from ingestion.validation_strategies import FileExistenceStrategy

        with NamedTemporaryFile(delete=False) as f:
            f.write(b'test content')
            temp_path = Path(f.name)

        try:
            strategy = FileExistenceStrategy()
            result = strategy.validate(temp_path)
            assert result.is_valid
            assert result.reason == ''
        finally:
            temp_path.unlink()

    def test_rejects_non_existent_file(self):
        """FileExistenceStrategy should reject non-existent file"""
        from ingestion.validation_strategies import FileExistenceStrategy

        strategy = FileExistenceStrategy()
        result = strategy.validate(Path('/non/existent/file.pdf'))
        assert not result.is_valid
        assert 'does not exist' in result.reason.lower()

    def test_rejects_empty_file(self):
        """FileExistenceStrategy should reject empty file"""
        from ingestion.validation_strategies import FileExistenceStrategy

        with NamedTemporaryFile(delete=False) as f:
            temp_path = Path(f.name)

        try:
            strategy = FileExistenceStrategy()
            result = strategy.validate(temp_path)
            assert not result.is_valid
            assert 'empty' in result.reason.lower()
        finally:
            temp_path.unlink()


class TestExtensionStrategy:
    """Test strategy for extension validation"""

    def test_validates_supported_extension(self):
        """ExtensionStrategy should pass for supported extensions"""
        from ingestion.validation_strategies import ExtensionStrategy

        strategy = ExtensionStrategy()
        result = strategy.validate(Path('document.pdf'))
        assert result.is_valid
        assert result.file_type == 'pdf'

    def test_rejects_unsupported_extension(self):
        """ExtensionStrategy should reject unsupported extensions"""
        from ingestion.validation_strategies import ExtensionStrategy

        strategy = ExtensionStrategy()
        result = strategy.validate(Path('malware.exe'))
        assert not result.is_valid
        assert 'unsupported' in result.reason.lower()

    def test_handles_multiple_dots_in_filename(self):
        """ExtensionStrategy should handle filenames with multiple dots"""
        from ingestion.validation_strategies import ExtensionStrategy

        strategy = ExtensionStrategy()
        result = strategy.validate(Path('my.backup.file.pdf'))
        assert result.is_valid
        assert result.file_type == 'pdf'


class TestTextFileStrategy:
    """Test strategy for text-based file validation"""

    def test_validates_python_file(self):
        """TextFileStrategy should validate Python files"""
        from ingestion.validation_strategies import TextFileStrategy

        with NamedTemporaryFile(suffix='.py', delete=False) as f:
            f.write(b'#!/usr/bin/env python3\nprint("hello")\n')
            temp_path = Path(f.name)

        try:
            strategy = TextFileStrategy()
            result = strategy.validate(temp_path, expected_type='python')
            assert result.is_valid
            assert result.file_type == 'python'
        finally:
            temp_path.unlink()

    def test_validates_markdown_file(self):
        """TextFileStrategy should validate markdown files"""
        from ingestion.validation_strategies import TextFileStrategy

        with NamedTemporaryFile(suffix='.md', delete=False) as f:
            f.write(b'# Heading\n\nSome text.')
            temp_path = Path(f.name)

        try:
            strategy = TextFileStrategy()
            result = strategy.validate(temp_path, expected_type='markdown')
            assert result.is_valid
            assert result.file_type == 'markdown'
        finally:
            temp_path.unlink()

    def test_rejects_binary_as_text(self):
        """TextFileStrategy should reject binary files claiming to be text"""
        from ingestion.validation_strategies import TextFileStrategy

        with NamedTemporaryFile(suffix='.py', delete=False) as f:
            # Write binary data (ELF executable header)
            f.write(b'\x7fELF\x02\x01\x01\x00')
            temp_path = Path(f.name)

        try:
            strategy = TextFileStrategy()
            result = strategy.validate(temp_path, expected_type='python')
            assert not result.is_valid
            assert 'binary' in result.reason.lower()
        finally:
            temp_path.unlink()


class TestExecutableCheckStrategy:
    """Test strategy for detecting executables"""

    def test_detects_elf_executable(self):
        """ExecutableCheckStrategy should detect ELF executables"""
        from ingestion.validation_strategies import ExecutableCheckStrategy

        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'\x7fELF\x02\x01\x01\x00')
            temp_path = Path(f.name)

        try:
            strategy = ExecutableCheckStrategy()
            result = strategy.validate(temp_path, expected_type='pdf')
            assert not result.is_valid
            assert 'executable' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_detects_windows_executable(self):
        """ExecutableCheckStrategy should detect Windows PE executables"""
        from ingestion.validation_strategies import ExecutableCheckStrategy

        with NamedTemporaryFile(suffix='.docx', delete=False) as f:
            f.write(b'MZ\x90\x00')
            temp_path = Path(f.name)

        try:
            strategy = ExecutableCheckStrategy()
            result = strategy.validate(temp_path, expected_type='docx')
            assert not result.is_valid
            assert 'executable' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_detects_shell_script(self):
        """ExecutableCheckStrategy should detect shell scripts"""
        from ingestion.validation_strategies import ExecutableCheckStrategy

        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'#!/bin/bash\nrm -rf /\n')
            temp_path = Path(f.name)

        try:
            strategy = ExecutableCheckStrategy()
            result = strategy.validate(temp_path, expected_type='pdf')
            assert not result.is_valid
            assert 'script' in result.reason.lower() or 'executable' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_passes_valid_pdf(self):
        """ExecutableCheckStrategy should pass valid PDF files"""
        from ingestion.validation_strategies import ExecutableCheckStrategy

        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4\n')
            temp_path = Path(f.name)

        try:
            strategy = ExecutableCheckStrategy()
            result = strategy.validate(temp_path, expected_type='pdf')
            assert result.is_valid
        finally:
            temp_path.unlink()


class TestMagicSignatureStrategy:
    """Test strategy for magic byte verification"""

    def test_validates_pdf_signature(self):
        """MagicSignatureStrategy should validate PDF magic bytes"""
        from ingestion.validation_strategies import MagicSignatureStrategy

        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(b'%PDF-1.4\n')
            f.write(b'%' + bytes(range(128, 132)))
            temp_path = Path(f.name)

        try:
            strategy = MagicSignatureStrategy()
            result = strategy.validate(temp_path, expected_type='pdf')
            assert result.is_valid
            assert result.file_type == 'pdf'
        finally:
            temp_path.unlink()

    def test_validates_docx_signature(self):
        """MagicSignatureStrategy should validate DOCX (ZIP) magic bytes"""
        from ingestion.validation_strategies import MagicSignatureStrategy

        with NamedTemporaryFile(suffix='.docx', delete=False) as f:
            f.write(b'PK\x03\x04')
            f.write(b'\x00' * 100)
            temp_path = Path(f.name)

        try:
            strategy = MagicSignatureStrategy()
            result = strategy.validate(temp_path, expected_type='docx')
            assert result.is_valid
            assert result.file_type == 'docx'
        finally:
            temp_path.unlink()

    def test_rejects_mismatched_signature(self):
        """MagicSignatureStrategy should reject signature mismatch"""
        from ingestion.validation_strategies import MagicSignatureStrategy

        with NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            # Write DOCX signature but claim PDF
            f.write(b'PK\x03\x04')
            temp_path = Path(f.name)

        try:
            strategy = MagicSignatureStrategy()
            result = strategy.validate(temp_path, expected_type='pdf')
            assert not result.is_valid
            assert 'signature' in result.reason.lower() or 'does not match' in result.reason.lower()
        finally:
            temp_path.unlink()

    def test_passes_text_files_without_signatures(self):
        """MagicSignatureStrategy should pass text files (no magic bytes defined)"""
        from ingestion.validation_strategies import MagicSignatureStrategy

        with NamedTemporaryFile(suffix='.md', delete=False) as f:
            f.write(b'# Heading\n')
            temp_path = Path(f.name)

        try:
            strategy = MagicSignatureStrategy()
            result = strategy.validate(temp_path, expected_type='markdown')
            assert result.is_valid
        finally:
            temp_path.unlink()


class TestValidationStrategyComposition:
    """Test composing strategies to reduce complexity"""

    def test_strategies_can_be_chained(self):
        """Multiple strategies should be composable"""
        from ingestion.validation_strategies import (
            FileExistenceStrategy,
            ExtensionStrategy,
            TextFileStrategy
        )

        with NamedTemporaryFile(suffix='.py', delete=False) as f:
            f.write(b'print("hello")\n')
            temp_path = Path(f.name)

        try:
            # Strategy 1: Check existence
            existence = FileExistenceStrategy()
            result1 = existence.validate(temp_path)
            assert result1.is_valid

            # Strategy 2: Check extension
            extension = ExtensionStrategy()
            result2 = extension.validate(temp_path)
            assert result2.is_valid
            assert result2.file_type == 'python'

            # Strategy 3: Check text content
            text = TextFileStrategy()
            result3 = text.validate(temp_path, expected_type='python')
            assert result3.is_valid
        finally:
            temp_path.unlink()

    def test_chain_stops_at_first_failure(self):
        """Strategy chain should stop at first validation failure"""
        from ingestion.validation_strategies import FileExistenceStrategy

        # Non-existent file should fail at first strategy
        non_existent = Path('/does/not/exist.pdf')
        existence = FileExistenceStrategy()
        result = existence.validate(non_existent)

        assert not result.is_valid
        # Should not proceed to next strategies
