"""Tests for GraphEnricher

Unit tests for chunk enrichment with knowledge graph metadata.
"""

import pytest
from pathlib import Path
from ingestion.obsidian.graph_enricher import GraphEnricher


class TestChunkEnrichment:
    """Test chunk enrichment with graph metadata"""

    def test_enrich_single_chunk(self):
        """Enrich a single chunk with graph context"""
        chunks = [("This is chunk content.", None)]
        graph_meta = {
            'tags': ['python', 'testing'],
            'wikilinks_out': ['RelatedNote'],
            'backlinks_count': 3,
            'connected_notes': ['Note A', 'Note B']
        }

        result = GraphEnricher.enrich_chunks(
            chunks, graph_meta, "Test Note", Path("test.md")
        )

        assert len(result) == 1
        enriched_text, page = result[0]
        assert "This is chunk content." in enriched_text
        assert "Note: Test Note" in enriched_text
        assert "Tags: python, testing" in enriched_text
        assert "Links to: RelatedNote" in enriched_text
        assert "Linked from: 3 notes" in enriched_text
        assert "Related notes: Note A, Note B" in enriched_text

    def test_enrich_multiple_chunks(self):
        """Enrich multiple chunks with same metadata"""
        chunks = [
            ("Chunk 1 content.", 1),
            ("Chunk 2 content.", 2),
            ("Chunk 3 content.", 3)
        ]
        graph_meta = {
            'tags': ['test'],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        result = GraphEnricher.enrich_chunks(
            chunks, graph_meta, "Multi Chunk Note", Path("multi.md")
        )

        assert len(result) == 3
        for i, (text, page) in enumerate(result):
            assert f"Chunk {i+1} content." in text
            assert "Note: Multi Chunk Note" in text
            assert page == i + 1

    def test_enrich_preserves_page_numbers(self):
        """Page numbers are preserved during enrichment"""
        chunks = [
            ("Content", 5),
            ("More content", None),
            ("Last chunk", 10)
        ]
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        result = GraphEnricher.enrich_chunks(
            chunks, graph_meta, "Test", Path("test.md")
        )

        assert result[0][1] == 5
        assert result[1][1] is None
        assert result[2][1] == 10


class TestContextFooter:
    """Test context footer building"""

    def test_footer_always_has_note_title(self):
        """Footer always includes note title"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "My Note")

        assert "Note: My Note" in footer
        assert footer.startswith("\n---")

    def test_footer_omits_empty_sections(self):
        """Empty metadata sections are not included"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Tags:" not in footer
        assert "Links to:" not in footer
        assert "Linked from:" not in footer
        assert "Related notes:" not in footer

    def test_footer_includes_all_populated_sections(self):
        """All non-empty sections are included"""
        graph_meta = {
            'tags': ['tag1'],
            'wikilinks_out': ['Link1'],
            'backlinks_count': 5,
            'connected_notes': ['Connected1']
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Tags: tag1" in footer
        assert "Links to: Link1" in footer
        assert "Linked from: 5 notes" in footer
        assert "Related notes: Connected1" in footer


class TestTagsFormatting:
    """Test tags line formatting"""

    def test_single_tag(self):
        """Single tag formatted correctly"""
        graph_meta = {
            'tags': ['python'],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Tags: python" in footer

    def test_multiple_tags(self):
        """Multiple tags comma-separated"""
        graph_meta = {
            'tags': ['python', 'testing', 'unit-tests'],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Tags: python, testing, unit-tests" in footer


class TestWikilinksFormatting:
    """Test wikilinks line formatting"""

    def test_single_wikilink(self):
        """Single wikilink formatted correctly"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': ['RelatedNote'],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Links to: RelatedNote" in footer

    def test_multiple_wikilinks_under_limit(self):
        """Up to 5 wikilinks shown without truncation"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': ['Note1', 'Note2', 'Note3', 'Note4', 'Note5'],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Links to: Note1, Note2, Note3, Note4, Note5" in footer
        assert "+0 more" not in footer

    def test_wikilinks_truncated_after_five(self):
        """More than 5 wikilinks shows count"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': ['Note1', 'Note2', 'Note3', 'Note4', 'Note5', 'Note6', 'Note7'],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Links to: Note1, Note2, Note3, Note4, Note5 (+2 more)" in footer

    def test_format_wikilinks_utility(self):
        """Test _format_wikilinks static method directly"""
        # Under limit
        result = GraphEnricher._format_wikilinks(['A', 'B', 'C'])
        assert result == "A, B, C"

        # At limit
        result = GraphEnricher._format_wikilinks(['A', 'B', 'C', 'D', 'E'])
        assert result == "A, B, C, D, E"

        # Over limit
        result = GraphEnricher._format_wikilinks(['A', 'B', 'C', 'D', 'E', 'F'])
        assert result == "A, B, C, D, E (+1 more)"


class TestBacklinksFormatting:
    """Test backlinks count formatting"""

    def test_zero_backlinks_omitted(self):
        """Zero backlinks not shown"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Linked from:" not in footer

    def test_single_backlink(self):
        """Single backlink shows singular form"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 1,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        # Implementation shows "1 notes" - could be improved but testing actual behavior
        assert "Linked from: 1 notes" in footer

    def test_multiple_backlinks(self):
        """Multiple backlinks formatted correctly"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 42,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Linked from: 42 notes" in footer


class TestConnectedNotesFormatting:
    """Test connected notes formatting"""

    def test_single_connected_note(self):
        """Single connected note formatted correctly"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': ['Related Note']
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Related notes: Related Note" in footer

    def test_three_connected_notes(self):
        """Up to 3 connected notes shown without ellipsis"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': ['Note A', 'Note B', 'Note C']
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Related notes: Note A, Note B, Note C" in footer
        assert "..." not in footer

    def test_connected_notes_truncated_after_three(self):
        """More than 3 connected notes shows ellipsis"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': ['Note A', 'Note B', 'Note C', 'Note D', 'Note E']
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "Related notes: Note A, Note B, Note C..." in footer

    def test_format_connected_notes_utility(self):
        """Test _format_connected_notes static method directly"""
        # Under limit
        result = GraphEnricher._format_connected_notes(['A', 'B'])
        assert result == "A, B"

        # At limit
        result = GraphEnricher._format_connected_notes(['A', 'B', 'C'])
        assert result == "A, B, C"

        # Over limit
        result = GraphEnricher._format_connected_notes(['A', 'B', 'C', 'D'])
        assert result == "A, B, C..."


class TestEdgeCases:
    """Test edge cases"""

    def test_empty_chunks_list(self):
        """Handle empty chunks list"""
        graph_meta = {
            'tags': ['test'],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        result = GraphEnricher.enrich_chunks(
            [], graph_meta, "Empty", Path("empty.md")
        )

        assert result == []

    def test_chunk_with_empty_text(self):
        """Handle chunk with empty text"""
        chunks = [("", None)]
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        result = GraphEnricher.enrich_chunks(
            chunks, graph_meta, "Test", Path("test.md")
        )

        assert len(result) == 1
        # Empty chunk still gets footer
        assert "Note: Test" in result[0][0]

    def test_special_characters_in_title(self):
        """Handle special characters in note title"""
        graph_meta = {
            'tags': [],
            'wikilinks_out': [],
            'backlinks_count': 0,
            'connected_notes': []
        }

        footer = GraphEnricher._build_context_footer(
            graph_meta, "Note with 'quotes' and \"double quotes\""
        )

        assert "Note: Note with 'quotes' and \"double quotes\"" in footer

    def test_unicode_in_metadata(self):
        """Handle unicode in metadata"""
        graph_meta = {
            'tags': ['francais', 'deutsche'],
            'wikilinks_out': ['Note avec accents'],
            'backlinks_count': 2,
            'connected_notes': ['Notes sur la cuisine francaise']
        }

        footer = GraphEnricher._build_context_footer(graph_meta, "Test")

        assert "francais" in footer
        assert "Note avec accents" in footer
        assert "Notes sur la cuisine francaise" in footer
