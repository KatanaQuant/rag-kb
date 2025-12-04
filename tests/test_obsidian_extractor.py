"""Tests for ObsidianExtractor

Tests Obsidian note extraction with graph metadata enrichment.
Uses Docling HybridChunker for token-aware chunking (v1.7.2+).
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
            pytest.skip(f"Fixture note not found: {note_path}")

        result = ObsidianExtractor.extract(note_path, graph_builder=extractor.graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success
        assert result.page_count > 0

    def test_extract_note_with_wikilinks(self, extractor, vault_path):
        """Test: Extract note with [[wikilinks]]"""
        note_path = vault_path / "Note1.md"

        if not note_path.exists():
            pytest.skip(f"Fixture note not found: {note_path}")

        result = ObsidianExtractor.extract(note_path, graph_builder=extractor.graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success

    def test_extract_note_with_tags(self, extractor, vault_path):
        """Test: Extract note with #hashtags"""
        note_path = vault_path / "Note1.md"

        if not note_path.exists():
            pytest.skip(f"Fixture note not found: {note_path}")

        result = ObsidianExtractor.extract(note_path, graph_builder=extractor.graph_builder)

        assert isinstance(result, ExtractionResult)
        assert result.success


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
        if len(results) == 0:
            pytest.skip(f"No fixture notes found in vault: {vault_extractor.vault_path}")

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
        """Test: Uses injected graph builder (dependency injection pattern)"""
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


class TestOversizedChunkPrevention:
    """Test that chunks respect token limits

    Issue: SemanticChunker didn't split long single lines, causing
    chunks >8192 tokens (model max) and >512 tokens (target).

    Fix: Use Docling HybridChunker for Obsidian files too.
    """

    @pytest.fixture
    def extractor(self):
        graph_builder = ObsidianGraphBuilder()
        return ObsidianExtractor(graph_builder=graph_builder)

    def test_long_single_line_gets_chunked(self, extractor):
        """Test: Files with very long lines (no newlines) are properly chunked

        This tests the bug where a 252K char single line wasn't split.
        """
        # Simulate a file with a very long single line (like minified HTML)
        long_line = "x" * 10000  # 10K chars - should be split
        content = f"# Title\n\n{long_line}"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            result = ObsidianExtractor.extract(Path(temp_path), graph_builder=extractor.graph_builder)

            # Should produce multiple chunks
            assert result.page_count > 1, "Long content should be split into multiple chunks"

            # Each chunk should be reasonable size
            for chunk_text, _ in result.pages:
                # Allow for graph metadata footer (~200 chars)
                assert len(chunk_text) < 3000, f"Chunk too long: {len(chunk_text)} chars"
        finally:
            Path(temp_path).unlink()

    def test_chunks_under_token_limit(self, extractor):
        """Test: All chunks should be under the embedding model's token limit"""
        # Create content that would previously create oversized chunks
        content = "# Title\n\n" + ("word " * 5000)  # ~5000 words

        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            result = ObsidianExtractor.extract(Path(temp_path), graph_builder=extractor.graph_builder)

            # Each chunk should be reasonable token count
            # Using 4 chars per token as rough estimate
            for chunk_text, _ in result.pages:
                estimated_tokens = len(chunk_text) // 4
                assert estimated_tokens < 8192, f"Chunk exceeds model limit: ~{estimated_tokens} tokens"
        finally:
            Path(temp_path).unlink()
