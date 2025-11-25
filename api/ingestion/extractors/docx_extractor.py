"""
DOCX file extractor

Extracts text from Microsoft Word DOCX files.
Extracted from extractors.py during modularization refactoring.
"""
from pathlib import Path
from docx import Document
from domain_models import ExtractionResult


class DOCXExtractor:
    """Extracts text from DOCX files"""

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract text from DOCX"""
        doc = Document(path)
        text = DOCXExtractor._join_paragraphs(doc)
        return ExtractionResult(pages=[(text, None)], method='docx')

    @staticmethod
    def _join_paragraphs(doc) -> str:
        """Join all paragraphs"""
        return '\n'.join([p.text for p in doc.paragraphs])
