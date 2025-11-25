"""
Text file extractor

Extracts text from plain text files.
Extracted from extractors.py during modularization refactoring.
"""
from pathlib import Path
from domain_models import ExtractionResult


class TextFileExtractor:
    """Extracts text from plain text files"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract text from file"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        return ExtractionResult(pages=[(text, None)], method='text')
