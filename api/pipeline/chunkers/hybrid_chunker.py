"""Hybrid chunker using Docling's HybridChunker.

Combines semantic understanding with structural awareness for optimal chunking.
This is the default and recommended chunker for most use cases.
"""

import logging
from typing import List, Dict, Optional

from pipeline.interfaces.chunker import ChunkerInterface

logger = logging.getLogger(__name__)


class HybridChunker(ChunkerInterface):
    """Hybrid semantic + structural chunker using Docling.

    Uses Docling's HybridChunker which combines:
    - Semantic understanding of content
    - Structural awareness (headings, paragraphs, code blocks)
    - Token-aware splitting to respect model limits

    This is the default chunker and works best for:
    - Documents (PDF, DOCX)
    - Markdown files
    - Mixed content with code and prose
    """

    def __init__(self, max_tokens: int = 512):
        """Initialize hybrid chunker.

        Args:
            max_tokens: Maximum tokens per chunk (default: 512)
        """
        self.max_tokens = max_tokens
        self._chunker = None

    @property
    def name(self) -> str:
        return "hybrid"

    def _get_docling_chunker(self):
        """Lazy-load Docling HybridChunker."""
        if self._chunker is None:
            try:
                from docling_core.transforms.chunker import HybridChunker as DoclingHybridChunker
                self._chunker = DoclingHybridChunker(
                    tokenizer="sentence",
                    max_tokens=self.max_tokens,
                    merge_peers=True
                )
            except ImportError as e:
                logger.warning(f"Docling HybridChunker not available: {e}")
                self._chunker = None
        return self._chunker

    def chunkify(self, source: str, **kwargs) -> List[Dict]:
        """Chunk text using Docling's hybrid strategy.

        Args:
            source: Source text to chunk
            **kwargs: Optional 'document' for pre-parsed Docling document

        Returns:
            List of chunk dictionaries with 'content' and 'metadata'
        """
        if not source or not source.strip():
            return []

        # If a Docling document is provided, use it directly
        document = kwargs.get('document')
        if document:
            return self._chunk_document(document)

        # Otherwise, fall back to simple chunking
        return self._chunk_text(source)

    def _chunk_document(self, document) -> List[Dict]:
        """Chunk a Docling document object."""
        chunker = self._get_docling_chunker()
        if chunker is None:
            return self._fallback_chunk(document.export_to_text() if hasattr(document, 'export_to_text') else str(document))

        chunks = []
        try:
            for chunk in chunker.chunk(document):
                chunk_text = chunk.text if hasattr(chunk, 'text') else str(chunk)
                if chunk_text.strip():
                    chunks.append({
                        'content': chunk_text,
                        'metadata': {'chunker': 'hybrid'}
                    })
        except Exception as e:
            logger.warning(f"Docling chunking failed: {e}, using fallback")
            return self._fallback_chunk(str(document))

        return chunks

    def _chunk_text(self, text: str) -> List[Dict]:
        """Chunk plain text (when no Docling document available)."""
        # For plain text, use paragraph-based chunking
        return self._fallback_chunk(text)

    def _fallback_chunk(self, text: str) -> List[Dict]:
        """Fallback chunking when Docling is not available."""
        # Simple paragraph-based chunking
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_size = 0
        # Approximate: 4 chars per token
        max_chars = self.max_tokens * 4

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_size = len(para)

            if current_size + para_size > max_chars and current_chunk:
                chunks.append({
                    'content': '\n\n'.join(current_chunk),
                    'metadata': {'chunker': 'hybrid_fallback'}
                })
                current_chunk = []
                current_size = 0

            current_chunk.append(para)
            current_size += para_size

        if current_chunk:
            chunks.append({
                'content': '\n\n'.join(current_chunk),
                'metadata': {'chunker': 'hybrid_fallback'}
            })

        return chunks
