"""Obsidian Note Extractor with Graph-RAG Support

Extracts and chunks Obsidian notes while building knowledge graph.
Combines:
- Semantic markdown chunking (Docling HybridChunker)
- Wikilink/tag extraction (obsidiantools)
- Knowledge graph construction (NetworkX)
- Graph-aware metadata enrichment

Follows Sandi Metz principles: small methods, single responsibility, <10 lines each.
"""

from pathlib import Path
from typing import List, Tuple, Dict, Optional
import re
import yaml

from domain_models import ExtractionResult
from ingestion.obsidian_graph import ObsidianGraphBuilder
from ingestion.obsidian.frontmatter_parser import FrontmatterParser
from ingestion.obsidian.semantic_chunker import SemanticChunker
from ingestion.obsidian.graph_enricher import GraphEnricher

try:
    import obsidiantools.api as obsidian_api
    OBSIDIANTOOLS_AVAILABLE = True
except ImportError:
    OBSIDIANTOOLS_AVAILABLE = False

class ObsidianExtractor:
    

    def __init__(self, graph_builder: Optional[ObsidianGraphBuilder] = None):
        
        self.graph_builder = graph_builder or ObsidianGraphBuilder()
        self.frontmatter_parser = FrontmatterParser()
        self.semantic_chunker = SemanticChunker()
        self.wikilink_pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
        self.tag_pattern = re.compile(r'#([\w/\-]+)')

    @staticmethod
    def extract(path: Path, graph_builder: Optional[ObsidianGraphBuilder] = None) -> ExtractionResult:
        """Extract Obsidian note with graph enrichment

        Args:
            path: Path to .md file
            graph_builder: Optional shared graph builder

        Returns:
            ExtractionResult with graph-enriched chunks
        """
        extractor = ObsidianExtractor(graph_builder)
        return extractor._extract_note(path)

    def _extract_note(self, path: Path) -> ExtractionResult:
        """Main extraction pipeline"""
        content = self._read_file(path)
        title = path.stem
        frontmatter = self.frontmatter_parser.extract_frontmatter(content)
        content_without_frontmatter = self.frontmatter_parser.remove_frontmatter(content)

        # Build graph node and edges
        node_id = self.graph_builder.add_note(path, title, content_without_frontmatter, frontmatter)

        # Extract graph metadata BEFORE chunking
        graph_meta = self._build_graph_metadata(node_id, content_without_frontmatter)

        # Semantic chunking with header awareness
        chunks = self.semantic_chunker.chunk(content_without_frontmatter, path)

        # Enrich each chunk with graph metadata
        enriched_chunks = GraphEnricher.enrich_chunks(chunks, graph_meta, title, path)

        return ExtractionResult(pages=enriched_chunks, method='obsidian_graph_rag')

    def _read_file(self, path: Path) -> str:
        """Read file content"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _build_graph_metadata(self, node_id: str, content: str) -> Dict:
        """Extract graph metadata for later enrichment

        Extracts but doesn't add to graph (already done in add_note)
        """
        wikilinks_out = self._extract_wikilinks(content)
        backlinks = self.graph_builder.get_backlinks(node_id)
        tags = self.graph_builder.get_tags_for_note(node_id)

        # Get connected notes (1-hop for context)
        connected_nodes = self.graph_builder.get_connected_nodes(
            node_id, hops=1, edge_types=['wikilink', 'backlink']
        )

        return {
            'node_id': node_id,
            'wikilinks_out': wikilinks_out,
            'backlinks_count': len(backlinks),
            'tags': tags,
            'connected_notes_count': len(connected_nodes),
            'connected_notes': [node['title'] for node in connected_nodes[:10]]  # Limit to 10
        }

    def _extract_wikilinks(self, content: str) -> List[str]:
        """Extract wikilink targets from content"""
        matches = self.wikilink_pattern.findall(content)
        return [target.strip() for target, _ in matches]

class ObsidianVaultExtractor:
    """Extracts entire Obsidian vault with shared knowledge graph

    Coordinates:
    1. Vault-wide graph building
    2. Per-note extraction with graph enrichment
    3. Graph export for persistence
    """

    def __init__(self, vault_path: Path):
        """Initialize vault extractor

        Args:
            vault_path: Path to Obsidian vault root directory
        """
        self.vault_path = vault_path
        self.graph_builder = ObsidianGraphBuilder()

    def extract_vault(self) -> Tuple[List[Tuple[Path, ExtractionResult]], ObsidianGraphBuilder]:
        """Extract all notes in vault

        Returns:
            Tuple of:
                - List of (file_path, ExtractionResult) pairs
                - Shared graph builder with complete vault graph
        """
        results = []
        md_files = list(self.vault_path.rglob('*.md'))

        for md_file in md_files:
            if self._should_skip(md_file):
                continue

            result = ObsidianExtractor.extract(md_file, self.graph_builder)
            results.append((md_file, result))

        return results, self.graph_builder

    def _should_skip(self, path: Path) -> bool:
        """Check if file should be skipped"""
        # Skip .obsidian folder and templates
        if '.obsidian' in path.parts:
            return True
        if 'templates' in path.parts:
            return True
        return False

    def save_graph(self, output_path: Path):
        """Save knowledge graph to JSON file"""
        self.graph_builder.save_to_file(output_path)

    def get_graph_stats(self) -> Dict:
        """Get graph statistics"""
        graph_data = self.graph_builder.export_graph()
        return graph_data['stats']
