# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Pipeline queue data structures for concurrent processing.

Follows Sandi Metz OOP principles:
- Single Responsibility: Each class represents one pipeline stage
- Small classes: < 100 lines
- Few instance variables: < 4
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
from queue import PriorityQueue

@dataclass(order=True)
class ExtractedDocument:
    """Document after extraction stage"""
    priority: int
    path: Path = field(compare=False)
    text: str = field(compare=False)
    metadata: dict = field(compare=False)
    force: bool = field(default=False, compare=False)

@dataclass(order=True)
class ChunkedDocument:
    """Document after chunking stage"""
    priority: int
    path: Path = field(compare=False)
    chunks: List[Dict] = field(compare=False)
    hash_val: str = field(compare=False)
    force: bool = field(default=False, compare=False)

@dataclass(order=True)
class EmbeddedDocument:
    """Document after embedding stage"""
    priority: int
    path: Path = field(compare=False)
    chunks: List[Dict] = field(compare=False)
    embeddings: List = field(compare=False)
    hash_val: str = field(compare=False)

class PipelineQueues:
    """Manages all queues for concurrent pipeline stages

    Architecture:
    - chunk_queue: Files ready for extraction+chunking (combined stage)
    - embed_queue: Chunked documents ready for embedding
    - store_queue: Embedded documents ready for storage
    """

    def __init__(self):
        self.chunk_queue = PriorityQueue()  # Extract+chunk combined
        self.embed_queue = PriorityQueue()
        self.store_queue = PriorityQueue()

    def get_stats(self) -> dict:
        """Get queue sizes for monitoring"""
        return {
            'chunk': self.chunk_queue.qsize(),
            'embed': self.embed_queue.qsize(),
            'store': self.store_queue.qsize()
        }

    def total_size(self) -> int:
        """Get total items across all queues"""
        stats = self.get_stats()
        return sum(stats.values())
