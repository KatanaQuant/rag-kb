"""
Extraction router.

Routes extraction requests to specialized extractors based on file type.
"""
from pathlib import Path
from typing import Dict

from config import default_config
from domain_models import ExtractionResult
from ingestion.extractors.docling_extractor import DoclingExtractor
from ingestion.extractors.epub_extractor import EpubExtractor
from ingestion.extractors.code_extractor import CodeExtractor
from ingestion.extractors.markdown_extractor import MarkdownExtractor
from ingestion.jupyter_extractor import JupyterExtractor
from ingestion.obsidian_extractor import ObsidianExtractor
from ingestion.obsidian_graph import ObsidianGraphBuilder
from ingestion.obsidian_detector import get_obsidian_detector


class ExtractionRouter:
    """Routes extraction requests to specialized extractors based on file type"""

    def __init__(self, config=default_config):
        self.config = config
        self.last_method = None  # Track which method was used
        self.obsidian_graph = ObsidianGraphBuilder()  # Shared graph for vault
        self.obsidian_detector = get_obsidian_detector()
        self.jupyter_extractor = JupyterExtractor()  # Instance for notebook extraction
        self.extractors = self._build_extractors()

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text based on file extension"""
        # Reset last_method to prevent stale values from previous extractions
        self.last_method = None

        ext = file_path.suffix.lower()
        self._validate_extension(ext)

        # Special handling for markdown: detect Obsidian vs regular
        if ext in ['.md', '.markdown']:
            return self._extract_markdown_intelligently(file_path)

        # Track which extraction method is being used
        method_map = {
            '.pdf': 'docling_hybrid',
            '.docx': 'docling_hybrid',
            '.epub': 'epub_pandoc_docling',
            '.py': 'ast_python',
            '.java': 'ast_java',
            '.ts': 'ast_typescript',
            '.tsx': 'ast_tsx',
            '.js': 'ast_javascript',
            '.jsx': 'ast_jsx',
            '.cs': 'ast_c_sharp',
            '.go': 'ast_go',
            '.ipynb': 'jupyter_ast'
        }
        self.last_method = method_map.get(ext, 'unknown')

        return self.extractors[ext](file_path)

    def _extract_markdown_intelligently(self, file_path: Path) -> ExtractionResult:
        """Choose between Obsidian Graph-RAG or regular markdown extraction"""
        if self.obsidian_detector.is_obsidian_note(file_path):
            self.last_method = 'obsidian_graph_rag'
            return ObsidianExtractor.extract(file_path, self.obsidian_graph)
        else:
            self.last_method = 'docling_markdown'
            return MarkdownExtractor.extract(file_path)

    def get_last_method(self) -> str:
        """Get the last extraction method used"""
        return self.last_method or 'unknown'

    def get_obsidian_graph(self) -> ObsidianGraphBuilder:
        """Get the shared Obsidian graph (for persistence)"""
        return self.obsidian_graph

    def _build_extractors(self) -> Dict:
        """Map extensions to extractors - Docling for docs, AST for code, Jupyter for notebooks, Graph-RAG for Obsidian"""
        print("Using Docling + HybridChunker for PDF/DOCX/EPUB/Markdown, AST chunking for code, Jupyter for .ipynb, Graph-RAG for Obsidian vaults")
        return {
            # Documents (Docling with semantic chunking)
            '.pdf': DoclingExtractor.extract,
            '.docx': DoclingExtractor.extract,
            '.epub': EpubExtractor.extract,
            '.md': DoclingExtractor.extract,
            '.markdown': DoclingExtractor.extract,
            # Code files (AST-based chunking)
            '.py': CodeExtractor.extract,
            '.java': CodeExtractor.extract,
            '.ts': CodeExtractor.extract,
            '.tsx': CodeExtractor.extract,
            '.js': CodeExtractor.extract,
            '.jsx': CodeExtractor.extract,
            '.cs': CodeExtractor.extract,
            '.go': CodeExtractor.extract,
            # Jupyter notebooks (AST + cell-aware chunking)
            '.ipynb': self.jupyter_extractor.extract
        }

    def _validate_extension(self, ext: str):
        """Validate extension is supported"""
        if ext not in self.extractors:
            raise ValueError(f"Unsupported: {ext}")
