"""
Docling document extractor

Extracts text from PDF and DOCX files using Docling library with advanced parsing.
Extracted from extractors.py during modularization refactoring.
"""
from pathlib import Path
from typing import ClassVar, List, Set, Tuple

from config import default_config
from domain_models import ExtractionResult
from ingestion.helpers import GhostscriptHelper
from ingestion.pdf_integrity import PDFIntegrityValidator
from ingestion.extractors._docling_availability import (
    DOCLING_AVAILABLE,
    DOCLING_CHUNKING_AVAILABLE
)
from pipeline.interfaces import ExtractorInterface


class DoclingExtractor(ExtractorInterface):
    """Extracts text from documents using Docling (advanced parsing)"""

    SUPPORTED_EXTENSIONS: ClassVar[Set[str]] = {'.pdf', '.docx'}

    _converter = None
    _chunker = None

    @property
    def name(self) -> str:
        return "docling"

    @classmethod
    def get_converter(cls):
        """Lazy load converter (singleton pattern)

        Uses Docling configuration from default_config.docling:
        - generate_page_images: Whether to generate page images (memory intensive)
        - generate_picture_images: Whether to generate picture images (memory intensive)
        - pdf_backend: PDF backend to use (dlparse_v4 or pypdfium2)

        Supports:
        - Text-based PDFs (direct text extraction)
        - Scanned/image-only PDFs (full OCR)
        - Hybrid PDFs with images containing text (text + OCR)
        - EasyOCR backend: Slow but accurate (default)
        - Table structure detection enabled (default)

        Note: RapidOCR warnings like "text detection result is empty" are
        normal when OCR checks images/pages and finds no text.
        """
        if cls._converter is None and DOCLING_AVAILABLE:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions

            # Configure PDF pipeline options from config
            pipeline_options = PdfPipelineOptions(
                generate_page_images=default_config.docling.generate_page_images,
                generate_picture_images=default_config.docling.generate_picture_images,
            )

            # Select PDF backend based on config
            if default_config.docling.pdf_backend == "pypdfium2":
                from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
                pdf_backend = PyPdfiumDocumentBackend
            else:
                # Default to dlparse_v4
                from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
                pdf_backend = DoclingParseV4DocumentBackend

            cls._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options,
                        backend=pdf_backend
                    )
                }
            )
        return cls._converter

    @classmethod
    def get_chunker(cls, max_tokens: int = 512):
        """Lazy load hybrid chunker (singleton pattern)"""
        if cls._chunker is None and DOCLING_CHUNKING_AVAILABLE:
            from docling_core.transforms.chunker import HybridChunker
            from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
            from transformers import AutoTokenizer

            # HybridChunker with HuggingFaceTokenizer wrapper
            raw_tokenizer = AutoTokenizer.from_pretrained(default_config.model.name)
            hf_tokenizer = HuggingFaceTokenizer(tokenizer=raw_tokenizer, max_tokens=max_tokens)
            cls._chunker = HybridChunker(tokenizer=hf_tokenizer, merge_peers=True)
        return cls._chunker

    def extract(self, path: Path, retry_with_ghostscript: bool = True) -> ExtractionResult:
        """Extract text from PDF/DOCX using Docling with HybridChunker

        Args:
            path: Path to PDF/DOCX file
            retry_with_ghostscript: If True, automatically retry with Ghostscript on failure

        Returns:
            ExtractionResult with pages extracted using Docling + HybridChunker

        Raises:
            ValueError: If PDF integrity check fails (corrupted/truncated file)
        """
        # Pre-flight integrity check for PDFs
        if path.suffix.lower() == '.pdf':
            DoclingExtractor._validate_pdf_integrity(path)

        try:
            return DoclingExtractor._convert_with_docling(path)
        except Exception as e:
            if DoclingExtractor._should_retry_with_ghostscript(path, retry_with_ghostscript):
                return DoclingExtractor._retry_after_ghostscript_fix(path, e)
            raise

    @staticmethod
    def _validate_pdf_integrity(path: Path) -> None:
        """Validate PDF integrity before extraction

        Raises:
            ValueError: If PDF is corrupted, truncated, or incomplete
        """
        result = PDFIntegrityValidator.validate(path)
        if not result.is_valid:
            raise ValueError(
                f"PDF integrity check failed for {path.name}: {result.error}"
            )

    @staticmethod
    def _convert_with_docling(path: Path) -> ExtractionResult:
        """Convert document using Docling"""
        import gc

        converter = DoclingExtractor.get_converter()
        result = converter.convert(str(path))

        DoclingExtractor._check_for_conversion_failure(result, path)

        document = result.document
        pages = DoclingExtractor._extract_hybrid_chunks(document)

        # Explicitly release large objects to reduce memory pressure
        # Critical for Mac Docker where memory limits are tight
        del document
        del result
        gc.collect()

        return ExtractionResult(pages=pages, method='docling')

    @staticmethod
    def _check_for_conversion_failure(result, path: Path):
        """Check if conversion failed and raise formatted error"""
        if hasattr(result, 'status'):
            from docling.datamodel.base_models import ConversionStatus
            if result.status == ConversionStatus.FAILURE:
                error_details = DoclingExtractor._extract_error_details(result)
                raise RuntimeError(
                    f"Docling conversion failed for: {path.name}\n"
                    f"  Status: FAILURE\n"
                    f"  Details:\n{error_details}"
                )

    @staticmethod
    def _extract_error_details(result) -> str:
        """Extract error messages from conversion result"""
        errors = []
        if hasattr(result, 'errors') and result.errors:
            for error in result.errors[:3]:  # Limit to first 3 errors
                errors.append(f"    - {str(error)}")
        return "\n".join(errors) if errors else "    - No specific error details available"

    @staticmethod
    def _should_retry_with_ghostscript(path: Path, retry_flag: bool) -> bool:
        """Determine if we should attempt Ghostscript retry"""
        return retry_flag and path.suffix.lower() == '.pdf'

    @staticmethod
    def _retry_after_ghostscript_fix(path: Path, original_error: Exception) -> ExtractionResult:
        """Attempt to fix PDF with Ghostscript and retry extraction"""
        error_reason = DoclingExtractor._get_condensed_error_reason(original_error)
        print(f"  → Docling failed ({error_reason}), attempting Ghostscript fix...")

        if not GhostscriptHelper.fix_pdf(path):
            print(f"  → Ghostscript fix failed")
            raise original_error

        print(f"  → Ghostscript succeeded, retrying extraction...")
        try:
            return DoclingExtractor.extract(path, retry_with_ghostscript=False)
        except Exception:
            print(f"  → Retry failed after Ghostscript fix")
            raise original_error

    @staticmethod
    def _get_condensed_error_reason(error: Exception) -> str:
        """Get first line of error message, condensed to 100 chars"""
        error_msg = str(error).split('\n')[0]
        return error_msg[:100] if error_msg else "Unknown error"

    @staticmethod
    def _extract_hybrid_chunks(document) -> List[Tuple[str, int]]:
        """Extract hybrid chunks using HybridChunker (structure + token-aware)"""
        chunker = DoclingExtractor.get_chunker(default_config.chunks.max_tokens)

        chunks_list = []
        chunk_iter = chunker.chunk(document)

        for chunk in chunk_iter:
            # Get chunk text (use text property or export to markdown)
            chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
            # Get page number from metadata if available
            page = chunk.meta.page if hasattr(chunk, 'meta') and hasattr(chunk.meta, 'page') else 0
            chunks_list.append((chunk_text, page))

        return chunks_list
