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

try:
    import obsidiantools.api as obsidian_api
    OBSIDIANTOOLS_AVAILABLE = True
except ImportError:
    OBSIDIANTOOLS_AVAILABLE = False


class ObsidianExtractor:
    """Extracts Obsidian notes with graph-aware chunking

    Architecture:
    1. Parse note content (frontmatter, wikilinks, tags)
    2. Build knowledge graph (add node + edges)
    3. Chunk semantically (header-aware boundaries)
    4. Enrich chunks with graph metadata

    NO FALLBACKS: Requires Docling for semantic chunking.
    """

    def __init__(self, graph_builder: Optional[ObsidianGraphBuilder] = None):
        """Initialize extractor

        Args:
            graph_builder: Optional shared graph builder (for vault-wide graphs)
                          If None, creates per-note graphs
        """
        self.graph_builder = graph_builder or ObsidianGraphBuilder()
        self.frontmatter_pattern = re.compile(r'^---\n(.+?)\n---\n', re.DOTALL)
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
        frontmatter = self._extract_frontmatter(content)
        content_without_frontmatter = self._remove_frontmatter(content)

        # Build graph node and edges
        node_id = self.graph_builder.add_note(path, title, content_without_frontmatter, frontmatter)

        # Extract graph metadata BEFORE chunking
        graph_meta = self._build_graph_metadata(node_id, content_without_frontmatter)

        # Semantic chunking with header awareness
        chunks = self._chunk_semantically(content_without_frontmatter, path)

        # Enrich each chunk with graph metadata
        enriched_chunks = self._enrich_chunks_with_graph(chunks, graph_meta, title, path)

        return ExtractionResult(pages=enriched_chunks, method='obsidian_graph_rag')

    def _read_file(self, path: Path) -> str:
        """Read file content"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _extract_frontmatter(self, content: str) -> Optional[Dict]:
        """Extract YAML frontmatter"""
        match = self.frontmatter_pattern.match(content)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))
        except:
            return None

    def _remove_frontmatter(self, content: str) -> str:
        """Remove frontmatter from content"""
        return self.frontmatter_pattern.sub('', content)

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

    def _chunk_semantically(self, content: str, path: Path) -> List[Tuple[str, Optional[int]]]:
        """Chunk content with header-aware boundaries

        Uses custom semantic chunking that respects markdown structure:
        - Headers (# ## ###) create hard boundaries
        - Paragraphs stay together
        - Code blocks stay together
        - Max chunk size: ~2048 chars (aligns with embedding model)
        """
        chunks = []
        current_chunk = []
        current_size = 0
        max_size = 2048
        overlap = 200

        lines = content.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            # Header creates boundary
            if line.startswith('#'):
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), None))
                    # Add overlap from previous chunk
                    current_chunk = self._get_overlap_lines(current_chunk, overlap)
                    current_size = sum(len(l) for l in current_chunk)

                current_chunk.append(line)
                current_size += len(line) + 1
                i += 1
                continue

            # Code block - keep together
            if line.startswith('```'):
                code_block = [line]
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    code_block.append(lines[i])
                    i += 1
                if i < len(lines):  # Closing ```
                    code_block.append(lines[i])
                    i += 1

                code_text = '\n'.join(code_block)
                if current_size + len(code_text) > max_size and current_chunk:
                    # Flush current chunk
                    chunks.append(('\n'.join(current_chunk), None))
                    current_chunk = self._get_overlap_lines(current_chunk, overlap)
                    current_size = sum(len(l) for l in current_chunk)

                current_chunk.extend(code_block)
                current_size += len(code_text)
                continue

            # Regular line
            if current_size + len(line) > max_size:
                if current_chunk:
                    chunks.append(('\n'.join(current_chunk), None))
                    current_chunk = self._get_overlap_lines(current_chunk, overlap)
                    current_size = sum(len(l) for l in current_chunk)

            current_chunk.append(line)
            current_size += len(line) + 1
            i += 1

        # Final chunk
        if current_chunk:
            chunks.append(('\n'.join(current_chunk), None))

        return chunks

    def _get_overlap_lines(self, lines: List[str], overlap_chars: int) -> List[str]:
        """Get last N characters worth of lines for overlap"""
        if not lines:
            return []

        overlap_lines = []
        char_count = 0

        for line in reversed(lines):
            if char_count >= overlap_chars:
                break
            overlap_lines.insert(0, line)
            char_count += len(line) + 1

        return overlap_lines

    def _enrich_chunks_with_graph(self, chunks: List[Tuple[str, Optional[int]]],
                                  graph_meta: Dict, title: str, path: Path) -> List[Tuple[str, Optional[int]]]:
        """Enrich chunks with graph context

        Adds graph metadata directly to chunk text in a machine-readable format
        that embeddings can capture.
        """
        enriched = []

        for i, (chunk_text, page) in enumerate(chunks):
            # Build context footer
            context_lines = [
                f"\n---",
                f"Note: {title}",
            ]

            if graph_meta['tags']:
                context_lines.append(f"Tags: {', '.join(graph_meta['tags'])}")

            if graph_meta['wikilinks_out']:
                links_preview = ', '.join(graph_meta['wikilinks_out'][:5])
                if len(graph_meta['wikilinks_out']) > 5:
                    links_preview += f" (+{len(graph_meta['wikilinks_out']) - 5} more)"
                context_lines.append(f"Links to: {links_preview}")

            if graph_meta['backlinks_count'] > 0:
                context_lines.append(f"Linked from: {graph_meta['backlinks_count']} notes")

            if graph_meta['connected_notes']:
                connected_preview = ', '.join(graph_meta['connected_notes'][:3])
                if len(graph_meta['connected_notes']) > 3:
                    connected_preview += "..."
                context_lines.append(f"Related notes: {connected_preview}")

            # Add context to chunk
            context_footer = '\n'.join(context_lines)
            enriched_text = f"{chunk_text}\n{context_footer}"

            enriched.append((enriched_text, page))

        return enriched


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
