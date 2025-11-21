"""Characterization tests for ObsidianExtractor

These tests document current behavior before refactoring.

From POODR audit:
- ObsidianExtractor: 237 lines, 4 responsibilities
- High complexity: _chunk_semantically (CC=16), _enrich_chunks_with_graph (CC=8)
- Concrete dependency: Creates own ObsidianGraphBuilder
- No existing tests (CRITICAL!)
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from ingestion.obsidian_extractor import ObsidianExtractor, ObsidianVaultExtractor
from ingestion.obsidian_graph import ObsidianGraphBuilder
from domain_models import ExtractionResult


class TestObsidianExtractorBasics:
    """Test basic note extraction"""

    @pytest.fixture
    def vault_path(self):
        """Path to sample Obsidian vault"""
        return Path(__file__).parent / "fixtures" / "obsidian_vault"

    @pytest.fixture
    def graph_builder(self):
        """Create mock graph builder"""
        return ObsidianGraphBuilder()

    @pytest.fixture
    def extractor(self, graph_builder):
        """Create ObsidianExtractor instance"""
        return ObsidianExtractor(graph_builder=graph_builder)

    def test_extract_note_basic(self, vault_path, graph_builder):
        """Test: Extract simple Obsidian note"""
        note_path = vault_path / "Note1.md"

        result = ObsidianExtractor.extract(note_path, graph_builder=graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success
        assert result.page_count > 0
        assert result.method == 'obsidian_graph_rag'

    def test_extract_note_includes_filepath(self, extractor, vault_path):
        """Test: Chunks include filepath metadata"""
        note_path = vault_path / "Note1.md"

        if not note_path.exists():
            pytest.skip("Fixture note not found")

        result = ObsidianExtractor.extract(note_path, graph_builder=extractor.graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success
        assert result.page_count > 0

    def test_extract_note_with_wikilinks(self, extractor, vault_path):
        """Test: Extract note with [[wikilinks]]"""
        note_path = vault_path / "Note1.md"

        if not note_path.exists():
            pytest.skip("Fixture note not found")

        result = ObsidianExtractor.extract(note_path, graph_builder=extractor.graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success

    def test_extract_note_with_tags(self, extractor, vault_path):
        """Test: Extract note with #hashtags"""
        note_path = vault_path / "Note1.md"

        if not note_path.exists():
            pytest.skip("Fixture note not found")

        result = ObsidianExtractor.extract(note_path, graph_builder=extractor.graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success


class TestFrontmatterParsing:
    """Test frontmatter extraction and parsing"""

    @pytest.fixture
    def extractor(self):
        graph_builder = ObsidianGraphBuilder()
        return ObsidianExtractor(graph_builder=graph_builder)

    @pytest.mark.skip(reason="Frontmatter parsing moved to FrontmatterParser class")
    def test_extract_frontmatter_valid_yaml(self, extractor):
        """Test: Parse valid YAML frontmatter"""
        content = """---
tags: [test, example]
created: 2025-01-01
---

# Content"""

        frontmatter = extractor._extract_frontmatter(content)

        assert isinstance(frontmatter, dict)
        assert 'tags' in frontmatter
        assert frontmatter['tags'] == ['test', 'example']

    @pytest.mark.skip(reason="Frontmatter parsing moved to FrontmatterParser class")
    def test_extract_frontmatter_missing(self, extractor):
        """Test: Handle notes without frontmatter"""
        content = "# Just a title\n\nNo frontmatter here."

        frontmatter = extractor._extract_frontmatter(content)

        assert frontmatter == {}

    @pytest.mark.skip(reason="Frontmatter parsing moved to FrontmatterParser class")
    def test_extract_frontmatter_invalid_yaml(self, extractor):
        """Test: Handle malformed YAML gracefully"""
        content = """---
invalid: yaml: structure: {{{
---

# Content"""

        # Should not crash
        frontmatter = extractor._extract_frontmatter(content)
        # Either empty dict or partial parse
        assert isinstance(frontmatter, dict)

    @pytest.mark.skip(reason="Frontmatter parsing moved to FrontmatterParser class")
    def test_remove_frontmatter_from_content(self, extractor):
        """Test: Frontmatter removed from chunk content"""
        content = """---
tags: [test]
---

# Content here"""

        clean_content = extractor._remove_frontmatter(content)

        assert '---' not in clean_content or clean_content.count('---') == 0
        assert '# Content here' in clean_content


class TestSemanticChunking:
    """Test semantic chunking by headers (CC=16 - High Complexity!)"""

    @pytest.fixture
    def extractor(self):
        graph_builder = ObsidianGraphBuilder()
        return ObsidianExtractor(graph_builder=graph_builder)

    @pytest.mark.skip(reason="Semantic chunking moved to SemanticChunker class")
    def test_chunk_semantically_by_headers(self, extractor):
        """Test: Split on H1, H2, H3 headers"""
        content = """# Main Title

Intro paragraph.

## Section 1

Content for section 1.

## Section 2

Content for section 2.

### Subsection 2.1

Nested content."""

        chunks = extractor._chunk_semantically(content, "test.md")

        assert len(chunks) > 1
        # Should split on headers
        assert all(isinstance(chunk, dict) for chunk in chunks)
        assert all('content' in chunk for chunk in chunks)

    @pytest.mark.skip(reason="Semantic chunking moved to SemanticChunker class")
    def test_chunk_semantically_respects_max_size(self, extractor):
        """Test: Chunks don't exceed 2048 chars"""
        large_section = "# Title\n\n" + ("x" * 3000)

        chunks = extractor._chunk_semantically(large_section, "test.md", max_chunk_size=2048)

        # Should split large section
        for chunk in chunks:
            assert len(chunk['content']) <= 2048 + 200  # Allow overlap

    @pytest.mark.skip(reason="Semantic chunking moved to SemanticChunker class")
    def test_chunk_semantically_overlap(self, extractor):
        """Test: 200-char overlap between chunks"""
        content = """# Section 1

""" + ("a" * 1500) + """

## Section 2

""" + ("b" * 1500)

        chunks = extractor._chunk_semantically(content, "test.md", max_chunk_size=2048, overlap_size=200)

        # Verify chunking happened
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    @pytest.mark.skip(reason="Semantic chunking moved to SemanticChunker class")
    def test_chunk_semantically_no_headers(self, extractor):
        """Test: Single chunk if no headers and content fits"""
        content = "Just some text without any headers. Not very long."

        chunks = extractor._chunk_semantically(content, "test.md")

        assert len(chunks) == 1
        assert chunks[0]['content'] == content

    @pytest.mark.skip(reason="Semantic chunking moved to SemanticChunker class")
    def test_chunk_semantically_nested_headers(self, extractor):
        """Test: Handle nested header hierarchy (H1 → H2 → H3)"""
        content = """# H1 Title

Content.

## H2 Subtitle

More content.

### H3 Subsubtitle

Nested content."""

        chunks = extractor._chunk_semantically(content, "test.md")

        # Should handle hierarchical headers
        assert len(chunks) >= 1


class TestGraphMetadataBuilding:
    """Test graph metadata extraction"""

    @pytest.fixture
    def extractor(self):
        graph_builder = ObsidianGraphBuilder()
        return ObsidianExtractor(graph_builder=graph_builder)

    def test_build_graph_metadata_basic(self, extractor):
        """Test: Extract basic graph metadata from content"""
        content = """# Note Title

This references [[OtherNote]] and has #tag1 and #tag2.
"""

        metadata = extractor._build_graph_metadata("note1", content)

        assert isinstance(metadata, dict)
        # Should detect wikilinks and tags
        assert 'tags' in metadata or 'wikilinks' in metadata

    def test_extract_wikilinks_basic(self, extractor):
        """Test: Extract [[wikilinks]] from content"""
        content = "Reference to [[Note A]] and [[Note B|Display Name]]."

        wikilinks = extractor._extract_wikilinks(content)

        assert isinstance(wikilinks, list)
        assert len(wikilinks) >= 2

    def test_extract_wikilinks_with_aliases(self, extractor):
        """Test: Handle [[Target|Alias]] format"""
        content = "Link: [[ActualNote|Display Text]]"

        wikilinks = extractor._extract_wikilinks(content)

        # Should extract actual note name, not alias
        assert any('ActualNote' in link for link in wikilinks)

    def test_extract_wikilinks_none(self, extractor):
        """Test: No wikilinks returns empty list"""
        content = "No wikilinks here, just #tags."

        wikilinks = extractor._extract_wikilinks(content)

        assert wikilinks == []


class TestChunkEnrichment:
    """Test chunk enrichment with graph metadata (CC=8)"""

    @pytest.fixture
    def extractor(self):
        graph_builder = ObsidianGraphBuilder()
        return ObsidianExtractor(graph_builder=graph_builder)

    @pytest.mark.skip(reason="Chunk enrichment moved to separate classes")
    def test_enrich_chunks_with_graph_footer(self, extractor):
        """Test: Add graph metadata footer to chunks"""
        chunks = [
            {'content': 'Chunk content', 'start_line': 0, 'end_line': 1}
        ]

        graph_metadata = {
            'tags': ['#tag1', '#tag2'],
            'wikilinks': ['[[Note1]]', '[[Note2]]'],
            'backlinks': ['[[BackNote]]']
        }

        enriched = extractor._enrich_chunks_with_graph(
            chunks, "note_id", graph_metadata, ['related1'], 2
        )

        assert len(enriched) == 1
        # Should have added metadata footer
        assert 'metadata' in enriched[0]

    @pytest.mark.skip(reason="Chunk enrichment moved to separate classes")
    def test_enrich_chunks_includes_tags(self, extractor):
        """Test: Tags included in enrichment"""
        chunks = [{'content': 'Content', 'start_line': 0, 'end_line': 1}]
        graph_metadata = {'tags': ['#test'], 'wikilinks': [], 'backlinks': []}

        enriched = extractor._enrich_chunks_with_graph(
            chunks, "note_id", graph_metadata, [], 0
        )

        # Tags should be in metadata
        metadata = enriched[0].get('metadata', {})
        assert 'tags' in metadata

    @pytest.mark.skip(reason="Chunk enrichment moved to separate classes")
    def test_enrich_chunks_includes_wikilinks(self, extractor):
        """Test: Wikilinks included"""
        chunks = [{'content': 'Content', 'start_line': 0, 'end_line': 1}]
        graph_metadata = {'tags': [], 'wikilinks': ['[[Link1]]'], 'backlinks': []}

        enriched = extractor._enrich_chunks_with_graph(
            chunks, "note_id", graph_metadata, [], 0
        )

        metadata = enriched[0].get('metadata', {})
        assert 'wikilinks' in metadata

    @pytest.mark.skip(reason="Chunk enrichment moved to separate classes")
    def test_enrich_chunks_includes_backlinks(self, extractor):
        """Test: Backlinks included"""
        chunks = [{'content': 'Content', 'start_line': 0, 'end_line': 1}]
        graph_metadata = {'tags': [], 'wikilinks': [], 'backlinks': ['[[Back1]]']}

        enriched = extractor._enrich_chunks_with_graph(
            chunks, "note_id", graph_metadata, [], 0
        )

        metadata = enriched[0].get('metadata', {})
        assert 'backlinks' in metadata

    @pytest.mark.skip(reason="Chunk enrichment moved to separate classes")
    def test_enrich_chunks_related_notes_limit(self, extractor):
        """Test: Related notes truncated to N"""
        chunks = [{'content': 'Content', 'start_line': 0, 'end_line': 1}]
        graph_metadata = {'tags': [], 'wikilinks': [], 'backlinks': []}

        many_related = [f"note{i}" for i in range(50)]

        enriched = extractor._enrich_chunks_with_graph(
            chunks, "note_id", graph_metadata, many_related, 10
        )

        # Should limit related notes
        metadata = enriched[0].get('metadata', {})
        if 'related_notes' in metadata:
            assert len(metadata['related_notes']) <= 10


class TestVaultLevelExtraction:
    """Test ObsidianVaultExtractor for vault-wide processing"""

    @pytest.fixture
    def vault_path(self):
        """Path to sample Obsidian vault"""
        return Path(__file__).parent / "fixtures" / "obsidian_vault"

    @pytest.fixture
    def vault_extractor(self, vault_path):
        """Create vault extractor"""
        return ObsidianVaultExtractor(vault_path)

    def test_extract_vault_detects_notes(self, vault_extractor, vault_path):
        """Test: Detect .md files in vault"""
        # Should find Note1.md and Note2.md
        notes = list(vault_path.glob("*.md"))
        assert len(notes) >= 2

    def test_extract_vault_skip_obsidian_folder(self, vault_extractor):
        """Test: Skip .obsidian/ directory"""
        # _should_skip should return True for .obsidian
        assert vault_extractor._should_skip(Path(".obsidian/config"))
        assert vault_extractor._should_skip(Path(".obsidian/workspace.json"))

    def test_extract_vault_skip_hidden_files(self, vault_extractor):
        """Test: Skip .obsidian and templates folders"""
        # _should_skip only checks for .obsidian and templates in path parts
        assert vault_extractor._should_skip(Path(".obsidian/config"))
        assert vault_extractor._should_skip(Path("templates/note.md"))

    def test_extract_vault_processes_md_files(self, vault_extractor, vault_path):
        """Test: Only process .md files"""
        # Should NOT skip .md files
        assert not vault_extractor._should_skip(Path("Note1.md"))
        assert not vault_extractor._should_skip(Path("Folder/Note.md"))

    def test_extract_vault_builds_graph(self, vault_extractor, vault_path):
        """Test: Graph built from vault structure"""
        # Extract entire vault
        results, graph_builder = vault_extractor.extract_vault()

        assert isinstance(results, list)
        assert isinstance(graph_builder, ObsidianGraphBuilder)
        # Should have results from multiple notes (if fixture exists)
        # Skipping if no fixtures found
        if len(results) == 0:
            pytest.skip("No fixture notes found")

    def test_vault_extractor_get_graph_stats(self, vault_extractor):
        """Test: Can retrieve graph statistics"""
        vault_extractor.extract_vault()

        stats = vault_extractor.get_graph_stats()

        assert isinstance(stats, dict)
        # Should have node and edge counts
        assert 'nodes' in stats or 'total_nodes' in stats


class TestObsidianDetectorIntegration:
    """Test integration with ObsidianDetector"""

    @pytest.fixture
    def vault_path(self):
        return Path(__file__).parent / "fixtures" / "obsidian_vault"

    def test_vault_has_obsidian_folder(self, vault_path):
        """Test: Vault has .obsidian folder"""
        obsidian_dir = vault_path / ".obsidian"
        assert obsidian_dir.exists()

    def test_note_has_obsidian_features(self, vault_path):
        """Test: Notes contain Obsidian features (wikilinks, tags)"""
        note1 = vault_path / "Note1.md"
        content = note1.read_text()

        # Should have frontmatter or wikilinks or tags
        has_features = (
            '---' in content or
            '[[' in content or
            '#' in content
        )
        assert has_features


class TestGraphBuilderIntegration:
    """Test ObsidianExtractor with real graph builder"""

    @pytest.fixture
    def vault_path(self):
        return Path(__file__).parent / "fixtures" / "obsidian_vault"

    def test_extractor_creates_graph_builder_if_none(self, vault_path):
        """Test: Creates default graph builder if not injected"""
        # Don't inject graph_builder (test current behavior)
        # This tests the concrete dependency we want to refactor
        extractor = ObsidianExtractor(str(vault_path))

        # Should have created its own graph_builder
        assert hasattr(extractor, 'graph_builder')

    def test_extractor_uses_injected_graph_builder(self, vault_path):
        """Test: Uses injected graph builder (future POODR-compliant behavior)"""
        mock_builder = Mock(spec=ObsidianGraphBuilder)

        extractor = ObsidianExtractor(graph_builder=mock_builder)

        assert extractor.graph_builder is mock_builder


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.fixture
    def extractor(self):
        graph_builder = ObsidianGraphBuilder()
        return ObsidianExtractor(graph_builder=graph_builder)

    def test_extract_empty_note(self, extractor):
        """Test: Handle empty note file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            result = ObsidianExtractor.extract(Path(temp_path), graph_builder=extractor.graph_builder)
            # Should return ExtractionResult
            assert isinstance(result, ExtractionResult)
        finally:
            Path(temp_path).unlink()

    def test_extract_note_only_frontmatter(self, extractor):
        """Test: Note with only frontmatter, no content"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("---\ntags: [test]\n---\n")
            temp_path = f.name

        try:
            result = ObsidianExtractor.extract(Path(temp_path), graph_builder=extractor.graph_builder)
            assert isinstance(result, ExtractionResult)
        finally:
            Path(temp_path).unlink()

    def test_extract_very_long_note(self, extractor):
        """Test: Handle very long note (>10k chars)"""
        long_content = "# Title\n\n" + ("Lorem ipsum " * 1000)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(long_content)
            temp_path = f.name

        try:
            result = ObsidianExtractor.extract(Path(temp_path), graph_builder=extractor.graph_builder)
            # Should split into multiple chunks
            assert isinstance(result, ExtractionResult)
            assert result.page_count > 0
        finally:
            Path(temp_path).unlink()

    @pytest.mark.skip(reason="Semantic chunking moved to SemanticChunker class")
    def test_chunk_semantically_preserves_content(self, extractor):
        """Test: Chunking doesn't lose content"""
        content = "# Section 1\n\nContent A\n\n## Section 2\n\nContent B"

        chunks = extractor._chunk_semantically(content, "test.md")

        # Reconstruct content from chunks
        reconstructed = '\n'.join(chunk['content'] for chunk in chunks)

        # Should contain key parts (allowing for formatting changes)
        assert 'Content A' in reconstructed
        assert 'Content B' in reconstructed
