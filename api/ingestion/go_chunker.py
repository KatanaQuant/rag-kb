"""Go code chunker using tree-sitter for AST-based chunking

This module provides AST-based chunking for Go code using tree-sitter-go directly,
since astchunk 0.1.0 doesn't support Go yet. Implements cAST algorithm principles:
- Syntactic integrity: respects function/type boundaries
- High information density: measured by non-whitespace chars
- Language invariance: works like other AST chunkers
"""

from typing import List, Dict
from pathlib import Path


class GoChunker:
    """AST-based chunker for Go code using tree-sitter

    Implements cAST algorithm similar to astchunk but for Go specifically.
    Uses tree-sitter-go parser to build AST and chunks by meaningful units.
    """

    def __init__(self, max_chunk_size: int = 2048, metadata_template: str = 'default'):
        """Initialize Go chunker with tree-sitter

        Args:
            max_chunk_size: Maximum chunk size in non-whitespace characters
            metadata_template: Metadata format ('none', 'default')
        """
        self.max_chunk_size = max_chunk_size
        self.metadata_template = metadata_template
        self._parser = None
        self._language = None

    def _get_parser(self):
        """Lazy load tree-sitter Go parser"""
        if self._parser is None:
            try:
                # Try py-tree-sitter-languages first (newer, more maintained)
                from tree_sitter_languages import get_language
                import tree_sitter
                lang = get_language('go')
                self._parser = tree_sitter.Parser(lang)
            except (ImportError, TypeError):
                # Fallback to tree-sitter-language-pack
                from tree_sitter_language_pack import get_parser
                self._parser = get_parser('go')
        return self._parser

    def _get_language(self):
        """Lazy load tree-sitter Go language"""
        if self._language is None:
            try:
                from tree_sitter_languages import get_language
                self._language = get_language('go')
            except (ImportError, TypeError):
                from tree_sitter_language_pack import get_language
                self._language = get_language('go')
        return self._language

    def _count_non_whitespace(self, text: str) -> int:
        """Count non-whitespace characters (cAST metric)"""
        return sum(1 for c in text if not c.isspace())

    def _extract_node_text(self, node, source_bytes: bytes) -> str:
        """Extract source text for a tree-sitter node"""
        return source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')

    def _is_chunkable_node(self, node) -> bool:
        """Determine if node is a chunkable unit (function, type, etc.)"""
        chunkable_types = {
            'function_declaration',
            'method_declaration',
            'type_declaration',
            'const_declaration',
            'var_declaration',
            'import_declaration',
            'package_clause',
        }
        return node.type in chunkable_types

    def _chunk_node(self, node, source_bytes: bytes, chunks: List[Dict]):
        """Recursively chunk AST node using cAST algorithm

        Algorithm:
        1. If node is chunkable and fits in max_size, create chunk
        2. If node is too large, recursively break into children
        3. Merge small adjacent chunks if they fit together
        """
        node_text = self._extract_node_text(node, source_bytes)
        node_size = self._count_non_whitespace(node_text)

        # If node is chunkable and fits, create chunk
        if self._is_chunkable_node(node) and node_size <= self.max_chunk_size:
            chunk = {
                'content': node_text,
                'metadata': {
                    'node_type': node.type,
                    'start_line': node.start_point[0] + 1,
                    'end_line': node.end_point[0] + 1,
                    'size': node_size,
                } if self.metadata_template == 'default' else {}
            }
            chunks.append(chunk)
            return

        # If node has children, recursively process them
        if node.child_count > 0:
            for child in node.children:
                self._chunk_node(child, source_bytes, chunks)
        elif node_size > 0:
            # Leaf node - create chunk even if large (will be truncated)
            chunk = {
                'content': node_text[:self.max_chunk_size * 4],  # Approx truncation
                'metadata': {
                    'node_type': node.type,
                    'start_line': node.start_point[0] + 1,
                    'end_line': node.end_point[0] + 1,
                    'size': min(node_size, self.max_chunk_size),
                    'truncated': node_size > self.max_chunk_size
                } if self.metadata_template == 'default' else {}
            }
            chunks.append(chunk)

    def chunkify(self, source_code: str) -> List[Dict]:
        """Chunk Go source code using AST

        Args:
            source_code: Go source code string

        Returns:
            List of chunk dictionaries with 'content' and 'metadata' keys
        """
        parser = self._get_parser()
        source_bytes = source_code.encode('utf-8')

        # Parse source code into AST
        tree = parser.parse(source_bytes)
        root = tree.root_node

        # Chunk AST nodes
        chunks = []
        self._chunk_node(root, source_bytes, chunks)

        # Filter out empty chunks
        chunks = [c for c in chunks if self._count_non_whitespace(c['content']) > 0]

        return chunks
