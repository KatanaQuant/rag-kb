"""
Code file extractor with AST-based chunking.

Extracts and chunks source code files using AST parsing.
"""
from pathlib import Path
from domain_models import ExtractionResult


class CodeExtractor:
    """Extracts code with AST-based chunking using astchunk

    NO FALLBACKS: If AST chunking fails, we fail explicitly.
    This ensures we never silently degrade to inferior text extraction.
    """

    _chunker_cache = {}  # Cache chunkers by language

    @staticmethod
    def _get_language(path: Path) -> str:
        """Detect programming language from file extension"""
        ext_to_lang = {
            '.py': 'python',
            '.java': 'java',
            '.ts': 'typescript',
            '.tsx': 'tsx',
            '.js': 'javascript',
            '.jsx': 'javascript',  # JSX parses fine with JavaScript parser
            '.cs': 'c_sharp',
            '.go': 'go',  # Go language support via tree-sitter-go
        }
        ext = path.suffix.lower()
        return ext_to_lang.get(ext, 'unknown')

    # Languages that need TreeSitterChunker (astchunk doesn't support them)
    TREE_SITTER_LANGUAGES = {'go', 'javascript', 'tsx'}

    @staticmethod
    def _get_chunker(language: str):
        """Get or create AST chunker for language

        Args:
            language: Programming language (python, java, typescript, go, etc.)

        Raises:
            ImportError: If required chunker library is not available (FAIL FAST)
            Exception: If chunker creation fails (FAIL FAST)
        """
        if language in CodeExtractor._chunker_cache:
            return CodeExtractor._chunker_cache[language]

        # Languages not supported by astchunk use TreeSitterChunker
        if language in CodeExtractor.TREE_SITTER_LANGUAGES:
            if language == 'go':
                # Go has specialized chunker with language-specific optimizations
                from ingestion.go_chunker import GoChunker
                chunker = GoChunker(max_chunk_size=2048, metadata_template='default')
            else:
                # JavaScript, TSX use generic TreeSitterChunker
                from ingestion.tree_sitter_chunker import TreeSitterChunker
                chunker = TreeSitterChunker(
                    language=language,
                    max_chunk_size=2048,
                    metadata_template='default'
                )
        else:
            # Python, Java, TypeScript use astchunk
            # NO try-except: Let import errors propagate
            from astchunk import ASTChunkBuilder

            # Create chunker with all required parameters
            # - max_chunk_size: 512 tokens ≈ 2048 chars (assuming 4 chars/token)
            # - language: programming language (python, java, etc.)
            # - metadata_template: 'default' includes filepath, chunk size, line numbers, node count
            #   Valid values: 'none', 'default', 'coderagbench-repoeval', 'coderagbench-swebench-lite'
            chunker = ASTChunkBuilder(
                max_chunk_size=2048,
                language=language,
                metadata_template='default'
            )

        CodeExtractor._chunker_cache[language] = chunker
        return chunker

    @staticmethod
    def extract(path: Path) -> ExtractionResult:
        """Extract code with AST-based chunking

        NO FALLBACKS: Raises exceptions if AST chunking fails.

        Returns:
            ExtractionResult with AST-chunked code blocks as pages

        Raises:
            ValueError: If language is unknown/unsupported
            ImportError: If astchunk is not available
            Exception: If AST parsing fails
        """
        language = CodeExtractor._get_language(path)

        if language == 'unknown':
            raise ValueError(f"Unsupported file extension: {path.suffix}")

        chunker = CodeExtractor._get_chunker(language)

        # Read source code
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            source_code = f.read()

        # Chunk with AST - NO try-except, let errors propagate
        # Note: language is already set in chunker, but chunkify may still need it
        result = chunker.chunkify(source_code)

        # Extract content from astchunk result format
        # astchunk returns list of dicts with 'content' and 'metadata' keys
        chunks = [chunk['content'] for chunk in result]

        # Convert chunks to pages format (text, page_number)
        # For code, we don't have page numbers, so use None
        pages = [(chunk, None) for chunk in chunks]

        return ExtractionResult(pages=pages, method=f'ast_{language}')
