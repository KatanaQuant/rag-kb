import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
import warnings

from pypdf import PdfReader
from docx import Document
import markdown
import numpy as np

from config import default_config
from hybrid_search import HybridSearcher
from domain_models import ChunkData, DocumentFile, ExtractionResult

# Suppress verbose Docling/PDF warnings and errors
logging.getLogger('pdfminer').setLevel(logging.CRITICAL)
logging.getLogger('PIL').setLevel(logging.CRITICAL)
logging.getLogger('docling').setLevel(logging.CRITICAL)
logging.getLogger('docling_parse').setLevel(logging.CRITICAL)
logging.getLogger('docling_core').setLevel(logging.CRITICAL)
logging.getLogger('pdfium').setLevel(logging.CRITICAL)
warnings.filterwarnings('ignore', category=UserWarning, module='pypdf')

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError as e:
    DOCLING_AVAILABLE = False
    print(f"Warning: Docling not available, falling back to pypdf ({e})")

# Try to import chunking separately (may not be available in all versions)
try:
    from docling_core.transforms.chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer
    DOCLING_CHUNKING_AVAILABLE = True
except ImportError as e:
    DOCLING_CHUNKING_AVAILABLE = False
    if DOCLING_AVAILABLE:
        print(f"Warning: Docling HybridChunker not available ({e}), using fixed-size chunking")

@dataclass

class ChunkingStrategy:
    """Base protocol for chunking strategies"""

    def __init__(self, config):
        self.config = config

    def chunk(self, text: str, page: int = None) -> List[ChunkData]:
        """Split text into chunks - must be implemented by subclasses"""
        raise NotImplementedError

    def _is_valid(self, chunk: str) -> bool:
        """Check if chunk meets minimum size"""
        return len(chunk.strip()) >= self.config.min_size

    def _make_chunk(self, content: str, page: int) -> ChunkData:
        """Create chunk data object"""
        return ChunkData(content=content, page=page)

class SemanticChunkingStrategy(ChunkingStrategy):
    """Semantic chunking: split on paragraphs/sentences, preserve structure"""

    def chunk(self, text: str, page: int = None) -> List[ChunkData]:
        """Split text into semantic chunks based on paragraphs"""
        paragraphs = self._split_into_paragraphs(text)
        chunks = self._build_chunks_from_paragraphs(paragraphs, page)
        return self._fallback_if_empty(chunks, text, page)

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text on paragraph boundaries"""
        return [p.strip() for p in text.split('\n\n') if p.strip()]

    def _build_chunks_from_paragraphs(self, paragraphs: List[str], page: int) -> List[ChunkData]:
        """Build chunks by combining paragraphs within size limit"""
        chunks = []
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            if self._should_start_new_chunk(current_chunk, current_size, len(para)):
                self._save_current_chunk(chunks, current_chunk, page)
                current_chunk = [para]
                current_size = len(para)
            else:
                current_chunk.append(para)
                current_size += len(para)

        self._save_current_chunk(chunks, current_chunk, page)
        return chunks

    def _should_start_new_chunk(self, current_chunk: List[str], current_size: int, para_size: int) -> bool:
        """Determine if we should start a new chunk"""
        return bool(current_chunk) and (current_size + para_size) > self.config.size

    def _save_current_chunk(self, chunks: List[ChunkData], current_chunk: List[str], page: int):
        """Save current chunk if valid"""
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if self._is_valid(chunk_text):
                chunks.append(self._make_chunk(chunk_text, page))

    def _fallback_if_empty(self, chunks: List[ChunkData], text: str, page: int) -> List[ChunkData]:
        """Fall back to fixed chunking if no semantic chunks created"""
        if not chunks:
            return FixedChunkingStrategy(self.config).chunk(text, page)
        return chunks

class FixedChunkingStrategy(ChunkingStrategy):
    """Fixed-size chunking with overlap"""

    def chunk(self, text: str, page: int = None) -> List[ChunkData]:
        """Split text into fixed-size chunks with overlap"""
        chunks = []
        start = 0
        while start < len(text):
            chunk = self._extract_chunk(text, start)
            if self._is_valid(chunk):
                chunks.append(self._make_chunk(chunk, page))
            start = self._next_position(start)
        return chunks

    def _extract_chunk(self, text: str, start: int) -> str:
        """Extract chunk at position"""
        end = start + self.config.size
        return text[start:end].strip()

    def _next_position(self, current: int) -> int:
        """Calculate next chunk start"""
        return current + self.config.size - self.config.overlap

class TextChunker:
    """Splits text into chunks (semantic or fixed-size)"""

    def __init__(self, config=default_config.chunks):
        self.config = config
        # Select strategy based on config
        if config.semantic:
            self.strategy = SemanticChunkingStrategy(config)
        else:
            self.strategy = FixedChunkingStrategy(config)

    def chunk(self, text: str, page: int = None) -> List[ChunkData]:
        """Split text into chunks using configured strategy"""
        return self.strategy.chunk(text, page)

