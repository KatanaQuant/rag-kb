"""
Tree-sitter based AST chunking for languages not supported by astchunk.

Implements chunking algorithm similar to ASTChunk but using tree-sitter-language-pack
to support additional languages like R.

Algorithm:
1. Parse code into AST using tree-sitter
2. Walk tree to find "chunkable" nodes (functions, classes, statements)
3. Split large nodes if they exceed max_chunk_size
4. Merge small adjacent siblings to fill chunks optimally
5. Preserve metadata about node types and positions
"""

from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass

@dataclass
class CodeChunk:
    """Represents a chunk of code with metadata"""
    content: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    node_type: str
    metadata: Dict[str, any]

class TreeSitterChunker:
    """Generic AST-based chunker using tree-sitter-languages

    Supports any language available in tree-sitter-languages (R, Python, etc.)
    Mimics ASTChunk's split-then-merge algorithm for consistent behavior.
    """

    # Node types that represent logical chunk boundaries
    # These vary by language but share common patterns
    CHUNKABLE_NODES = {
        'r': {
            'function_definition',
            'binary_operator',  # Assignment with <-
            'call',  # Function calls
            'for_statement',
            'while_statement',
            'if_statement',
            'braced_expression',  # { ... } blocks
        },
        'python': {
            'function_definition',
            'class_definition',
            'decorated_definition',
            'for_statement',
            'while_statement',
            'if_statement',
            'with_statement',
            'try_statement',
        }
    }

    def __init__(
        self,
        language: str,
        max_chunk_size: int = 2048,
        chunk_overlap: int = 0,
        metadata_template: str = 'default'
    ):
        """Initialize chunker for a specific language

        Args:
            language: Language name (e.g., 'r', 'python')
            max_chunk_size: Maximum characters per chunk
            chunk_overlap: Number of characters to overlap between chunks
            metadata_template: Format for metadata output
        """
        self.language = language.lower()
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.metadata_template = metadata_template

        # Lazy load parser
        self._parser = None
        self._tree_sitter = None

    def _get_parser(self):
        """Lazy load tree-sitter parser for language"""
        if self._parser is None:
            try:
                from tree_sitter_language_pack import get_language, get_parser
                # Get language and create parser
                language = get_language(self.language)
                self._parser = get_parser(self.language)
            except ImportError as e:
                raise ImportError(
                    f"tree-sitter-language-pack not available: {e}\n"
                    "Install with: pip install tree-sitter-language-pack>=0.10.0"
                )
            except Exception as e:
                raise ValueError(
                    f"Failed to load parser for language '{self.language}': {e}\n"
                    f"Supported languages: python, r, javascript, java, etc. (160+ languages)\n"
                    f"See: https://pypi.org/project/tree-sitter-language-pack/"
                )
        return self._parser

    def _parse_code(self, code: str):
        """Parse code into AST tree"""
        parser = self._get_parser()
        tree = parser.parse(bytes(code, 'utf8'))
        return tree

    def _walk_tree(self, node, code_bytes: bytes) -> List[CodeChunk]:
        """Walk AST tree and extract chunks

        Implements split-then-merge algorithm:
        1. Identify chunkable nodes
        2. Split nodes that exceed max size
        3. Merge small adjacent nodes

        Args:
            node: Tree-sitter node to walk
            code_bytes: Original code as bytes

        Returns:
            List of code chunks
        """
        chunks = []
        chunkable_types = self.CHUNKABLE_NODES.get(self.language, set())

        # Check if this node is a chunkable boundary
        if node.type in chunkable_types:
            chunk_content = code_bytes[node.start_byte:node.end_byte].decode('utf8')
            chunk_size = len(chunk_content)

            # If node fits in one chunk, take it
            if chunk_size <= self.max_chunk_size:
                chunk = CodeChunk(
                    content=chunk_content,
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                    start_line=node.start_point[0] + 1,  # 0-indexed to 1-indexed
                    end_line=node.end_point[0] + 1,
                    node_type=node.type,
                    metadata=self._build_metadata(node, chunk_content)
                )
                chunks.append(chunk)
            else:
                # Node too large, recurse into children
                for child in node.children:
                    chunks.extend(self._walk_tree(child, code_bytes))
        else:
            # Not a chunkable node, recurse into children
            for child in node.children:
                chunks.extend(self._walk_tree(child, code_bytes))

        return chunks

    def _merge_small_chunks(self, chunks: List[CodeChunk], code: str) -> List[CodeChunk]:
        """Merge adjacent small chunks to optimize chunk size

        Greedy merging: combine adjacent chunks until max_chunk_size is reached

        Args:
            chunks: List of chunks to merge
            code: Original code string

        Returns:
            List of merged chunks
        """
        if not chunks:
            return []

        merged = []
        current_chunks = [chunks[0]]
        current_size = len(chunks[0].content)

        for chunk in chunks[1:]:
            chunk_size = len(chunk.content)

            # Check if we can merge this chunk
            # Use start/end bytes to get exact content between chunks
            if current_chunks:
                gap_start = current_chunks[-1].end_byte
                gap_end = chunk.start_byte
                gap_content = code[gap_start:gap_end] if gap_end > gap_start else ""
                combined_size = current_size + len(gap_content) + chunk_size
            else:
                combined_size = chunk_size
                gap_content = ""

            if combined_size <= self.max_chunk_size:
                # Merge: add chunk to current group
                current_chunks.append(chunk)
                current_size = combined_size
            else:
                # Can't merge: finalize current group and start new
                if current_chunks:
                    merged.append(self._combine_chunks(current_chunks, code))
                current_chunks = [chunk]
                current_size = chunk_size

        # Add last group
        if current_chunks:
            merged.append(self._combine_chunks(current_chunks, code))

        return merged

    def _combine_chunks(self, chunks: List[CodeChunk], code: str) -> CodeChunk:
        """Combine multiple chunks into one

        Args:
            chunks: Chunks to combine (must be adjacent)
            code: Original code string

        Returns:
            Single combined chunk
        """
        if len(chunks) == 1:
            return chunks[0]

        # Get combined content from start of first to end of last
        start_byte = chunks[0].start_byte
        end_byte = chunks[-1].end_byte
        content = code[start_byte:end_byte]

        # Combine metadata
        node_types = [c.node_type for c in chunks]

        return CodeChunk(
            content=content,
            start_byte=start_byte,
            end_byte=end_byte,
            start_line=chunks[0].start_line,
            end_line=chunks[-1].end_line,
            node_type='+'.join(node_types),  # e.g., "function+function+if_statement"
            metadata={
                'combined_chunks': len(chunks),
                'node_types': node_types,
                'start_line': chunks[0].start_line,
                'end_line': chunks[-1].end_line,
            }
        )

    def _build_metadata(self, node, content: str) -> Dict:
        """Build metadata for a chunk

        Args:
            node: Tree-sitter node
            content: Chunk content

        Returns:
            Metadata dictionary
        """
        if self.metadata_template == 'none':
            return {}

        # Default metadata similar to ASTChunk
        metadata = {
            'chunk_size': len(content),
            'node_type': node.type,
            'start_line': node.start_point[0] + 1,
            'end_line': node.end_point[0] + 1,
            'start_column': node.start_point[1],
            'end_column': node.end_point[1],
        }

        return metadata

    def chunkify(self, code: str, filepath: Optional[str] = None) -> List[Dict]:
        """Chunk code into AST-aware segments"""
        if not code or not code.strip():
            return []

        tree = self._parse_code(code)
        code_bytes = bytes(code, 'utf8')
        raw_chunks = self._extract_raw_chunks(tree, code_bytes, code)
        merged_chunks = self._merge_small_chunks(raw_chunks, code)

        return self._format_chunks_as_dicts(merged_chunks, filepath)

    def _extract_raw_chunks(self, tree, code_bytes: bytes, code: str) -> List[CodeChunk]:
        """Extract initial chunks from AST"""
        raw_chunks = self._walk_tree(tree.root_node, code_bytes)
        return raw_chunks if raw_chunks else self._create_fallback_chunk(code, code_bytes)

    def _create_fallback_chunk(self, code: str, code_bytes: bytes) -> List[CodeChunk]:
        """Create single chunk when no chunkable nodes found"""
        return [CodeChunk(
            content=code,
            start_byte=0,
            end_byte=len(code_bytes),
            start_line=1,
            end_line=code.count('\n') + 1,
            node_type='module',
            metadata={'note': 'no chunkable nodes found'}
        )]

    def _format_chunks_as_dicts(self, chunks: List[CodeChunk], filepath: Optional[str]) -> List[Dict]:
        """Convert CodeChunk objects to dict format"""
        return [self._format_single_chunk(chunk, i, filepath) for i, chunk in enumerate(chunks)]

    def _format_single_chunk(self, chunk: CodeChunk, index: int, filepath: Optional[str]) -> Dict:
        """Format single chunk as dictionary"""
        chunk_dict = {
            'content': chunk.content,
            'metadata': {
                **chunk.metadata,
                'chunk_index': index,
                'language': self.language,
            }
        }

        if filepath:
            chunk_dict['metadata']['filepath'] = filepath

        return chunk_dict

def chunk_code_with_treesitter(
    code: str,
    language: str,
    max_chunk_size: int = 2048,
    filepath: Optional[str] = None
) -> List[Dict]:
    """Convenience function for chunking code with tree-sitter

    Args:
        code: Source code to chunk
        language: Language name ('r', 'python', etc.)
        max_chunk_size: Maximum characters per chunk
        filepath: Optional filepath for metadata

    Returns:
        List of chunk dictionaries

    Example:
        >>> chunks = chunk_code_with_treesitter(r_code, 'r', max_chunk_size=2048)
        >>> for chunk in chunks:
        >>>     print(f"Chunk ({chunk['metadata']['start_line']}-{chunk['metadata']['end_line']}):")
        >>>     print(chunk['content'])
    """
    chunker = TreeSitterChunker(
        language=language,
        max_chunk_size=max_chunk_size,
        metadata_template='default'
    )
    return chunker.chunkify(code, filepath=filepath)
