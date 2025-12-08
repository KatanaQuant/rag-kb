"""Tests for Obsidian graph cleanup on reindexing

Tests the critical flow:
1. Index Obsidian note → creates graph nodes
2. Modify note → change hash
3. Reindex → old nodes cleaned up properly
4. Verify: No orphan nodes remain

NOTE: These tests require sqlite-vec extension for graph storage.
They are skipped when the extension is not available.
"""

import pytest
import sqlite3
from pathlib import Path
import tempfile
import shutil


def _has_sqlite_vec():
    """Check if sqlite-vec extension is available and loadable."""
    try:
        import sqlite_vec
        import sqlite3
        conn = sqlite3.connect(':memory:')
        sqlite_vec.load(conn)
        conn.close()
        return True
    except (ImportError, AttributeError, Exception):
        return False


# Skip all tests if sqlite-vec not available
pytestmark = pytest.mark.skipif(
    not _has_sqlite_vec(),
    reason="sqlite-vec extension not available"
)

from ingestion.graph_repository import GraphRepository
from ingestion.database import DatabaseConnection, SchemaManager


class TestObsidianGraphCleanup:
    """Test graph cleanup when Obsidian notes are reindexed"""

    @pytest.fixture
    def db_conn(self):
        """Create in-memory database with schema"""
        import sqlite_vec

        conn = sqlite3.connect(':memory:')

        # Enable foreign keys (required for CASCADE DELETE)
        conn.execute("PRAGMA foreign_keys = ON")

        # Load sqlite-vec
        sqlite_vec.load(conn)

        # Create schema
        from config import DatabaseConfig
        config = DatabaseConfig(path=':memory:', embedding_dim=1024)
        schema = SchemaManager(conn, config)
        schema.create_schema()

        yield conn
        conn.close()

    @pytest.fixture
    def graph_repo(self, db_conn):
        """Create graph repository"""
        return GraphRepository(db_conn)

    def test_note_node_deleted_on_reindex(self, graph_repo):
        """Test: Note-specific graph node is deleted when note reindexed"""
        # Setup: Create note node
        note_path = "/vault/Note.md"
        node_id = f"note:{note_path}"
        graph_repo.save_node(node_id, "note", "Note", "Content")
        graph_repo.commit()

        # Verify node exists
        node = graph_repo.get_node(node_id)
        assert node is not None
        assert node['title'] == "Note"

        # Action: Delete note node (simulating reindex)
        graph_repo.delete_note_nodes(note_path)
        graph_repo.commit()

        # Verify: Node deleted
        node = graph_repo.get_node(node_id)
        assert node is None

    def test_tag_node_persists_with_other_references(self, graph_repo):
        """Test: Tag node persists if other notes still reference it"""
        # Setup: Two notes, one tag
        note1_id = "note:/vault/Note1.md"
        note2_id = "note:/vault/Note2.md"
        tag_id = "tag:python"

        graph_repo.save_node(note1_id, "note", "Note1", "Content1")
        graph_repo.save_node(note2_id, "note", "Note2", "Content2")
        graph_repo.save_node(tag_id, "tag", "#python")

        # Both notes tag #python
        graph_repo.save_edge(note1_id, tag_id, "tag")
        graph_repo.save_edge(note2_id, tag_id, "tag")
        graph_repo.commit()

        # Action: Delete note1 (reindex)
        graph_repo.delete_note_nodes("/vault/Note1.md")
        graph_repo.commit()

        # Verify: Tag still exists (note2 references it)
        tag = graph_repo.get_node(tag_id)
        assert tag is not None
        assert tag['title'] == "#python"

    def test_tag_node_deleted_when_no_references(self, graph_repo):
        """Test: Tag node deleted when last note referencing it is deleted"""
        # Setup: One note, one tag
        note_id = "note:/vault/Note.md"
        tag_id = "tag:python"

        graph_repo.save_node(note_id, "note", "Note", "Content")
        graph_repo.save_node(tag_id, "tag", "#python")
        graph_repo.save_edge(note_id, tag_id, "tag")
        graph_repo.commit()

        # Action: Delete note (simulating reindex)
        graph_repo.delete_note_nodes("/vault/Note.md")
        graph_repo.commit()

        # Verify: Tag also deleted (no references remain)
        tag = graph_repo.get_node(tag_id)
        assert tag is None

    def test_edges_cascade_deleted_with_node(self, graph_repo):
        """Test: Edges are CASCADE deleted when node is deleted"""
        # Setup: Two notes with wikilink
        note1_id = "note:/vault/Note1.md"
        note2_id = "note:/vault/Note2.md"

        graph_repo.save_node(note1_id, "note", "Note1", "Content1")
        graph_repo.save_node(note2_id, "note", "Note2", "Content2")
        graph_repo.save_edge(note1_id, note2_id, "wikilink")
        graph_repo.commit()

        # Verify edge exists
        edges = graph_repo.get_edges_from(note1_id)
        assert len(edges) == 1

        # Action: Delete note1
        graph_repo.delete_note_nodes("/vault/Note1.md")
        graph_repo.commit()

        # Verify: Edge deleted via CASCADE
        edges = graph_repo.get_edges_from(note1_id)
        assert len(edges) == 0

    def test_renamed_note_creates_new_node(self, graph_repo):
        """Test: Renaming note (old deleted, new created) doesn't leave orphans"""
        # Setup: Index note with old name
        old_path = "/vault/OldName.md"
        old_node_id = f"note:{old_path}"
        tag_id = "tag:python"

        graph_repo.save_node(old_node_id, "note", "OldName", "Content")
        graph_repo.save_node(tag_id, "tag", "#python")
        graph_repo.save_edge(old_node_id, tag_id, "tag")
        graph_repo.commit()

        # Action: User renames file → reindex deletes old, creates new
        graph_repo.delete_note_nodes(old_path)

        new_path = "/vault/NewName.md"
        new_node_id = f"note:{new_path}"
        graph_repo.save_node(new_node_id, "note", "NewName", "Content")
        # Tag was deleted with old note, need to recreate it
        graph_repo.save_node(tag_id, "tag", "#python")
        graph_repo.save_edge(new_node_id, tag_id, "tag")  # Re-tag in new note
        graph_repo.commit()

        # Verify: Old node gone, new node exists, tag persists
        old_node = graph_repo.get_node(old_node_id)
        assert old_node is None

        new_node = graph_repo.get_node(new_node_id)
        assert new_node is not None
        assert new_node['title'] == "NewName"

        tag = graph_repo.get_node(tag_id)
        assert tag is not None  # Tag persists

    def test_header_nodes_deleted_with_parent_note(self, graph_repo):
        """Test: Header nodes (children of note) are deleted with parent"""
        # Setup: Note with header hierarchy
        note_id = "note:/vault/Note.md"
        header1_id = f"{note_id}:h0"
        header2_id = f"{note_id}:h1"

        graph_repo.save_node(note_id, "note", "Note", "Content")
        graph_repo.save_node(header1_id, "header", "Introduction", metadata={'level': 1})
        graph_repo.save_node(header2_id, "header", "Details", metadata={'level': 2})
        graph_repo.save_edge(note_id, header1_id, "header_child")
        graph_repo.save_edge(header1_id, header2_id, "header_child")
        graph_repo.commit()

        # Action: Delete note
        graph_repo.delete_note_nodes("/vault/Note.md")
        graph_repo.commit()

        # Verify: All header nodes deleted
        assert graph_repo.get_node(note_id) is None
        assert graph_repo.get_node(header1_id) is None
        assert graph_repo.get_node(header2_id) is None

    def test_multiple_notes_same_tag_cleanup(self, graph_repo):
        """Test: Tag reference counting with multiple notes"""
        # Setup: 3 notes, all with #python tag
        note_ids = [f"note:/vault/Note{i}.md" for i in range(3)]
        tag_id = "tag:python"

        graph_repo.save_node(tag_id, "tag", "#python")
        for note_id in note_ids:
            graph_repo.save_node(note_id, "note", note_id.split('/')[-1], "Content")
            graph_repo.save_edge(note_id, tag_id, "tag")
        graph_repo.commit()

        # Action: Delete 2 notes
        graph_repo.delete_note_nodes("/vault/Note0.md")
        graph_repo.delete_note_nodes("/vault/Note1.md")
        graph_repo.commit()

        # Verify: Tag still exists (1 reference remains)
        tag = graph_repo.get_node(tag_id)
        assert tag is not None

        # Action: Delete last note
        graph_repo.delete_note_nodes("/vault/Note2.md")
        graph_repo.commit()

        # Verify: Tag now deleted (no references)
        tag = graph_repo.get_node(tag_id)
        assert tag is None

    def test_wikilink_orphan_cleanup(self, graph_repo):
        """Test: Placeholder nodes (wikilink targets) are cleaned up"""
        # Setup: Note with wikilink to non-existent note
        note_id = "note:/vault/Source.md"
        target_ref = "note_ref:Target"  # Placeholder for [[Target]]

        graph_repo.save_node(note_id, "note", "Source", "Content with [[Target]]")
        graph_repo.save_node(target_ref, "note_ref", "Target", metadata={'placeholder': True})
        graph_repo.save_edge(note_id, target_ref, "wikilink")
        graph_repo.commit()

        # Action: Delete source note
        graph_repo.delete_note_nodes("/vault/Source.md")
        graph_repo.commit()

        # Verify: Placeholder target also deleted (no references)
        target = graph_repo.get_node(target_ref)
        assert target is None


class TestGraphRepositoryCleanupMethods:
    """Test the cleanup methods themselves"""

    @pytest.fixture
    def db_conn(self):
        """Create in-memory database"""
        import sqlite_vec

        conn = sqlite3.connect(':memory:')
        sqlite_vec.load(conn)

        from config import DatabaseConfig
        config = DatabaseConfig(path=':memory:', embedding_dim=1024)
        schema = SchemaManager(conn, config)
        schema.create_schema()

        yield conn
        conn.close()

    @pytest.fixture
    def graph_repo(self, db_conn):
        return GraphRepository(db_conn)

    def test_delete_note_nodes_method_exists(self, graph_repo):
        """Test: delete_note_nodes method is implemented"""
        assert hasattr(graph_repo, 'delete_note_nodes')
        assert callable(getattr(graph_repo, 'delete_note_nodes'))

    def test_cleanup_orphan_tags_method_exists(self, graph_repo):
        """Test: cleanup_orphan_tags method is implemented"""
        assert hasattr(graph_repo, 'cleanup_orphan_tags')
        assert callable(getattr(graph_repo, 'cleanup_orphan_tags'))

    def test_cleanup_orphan_placeholders_method_exists(self, graph_repo):
        """Test: cleanup_orphan_placeholders method is implemented"""
        assert hasattr(graph_repo, 'cleanup_orphan_placeholders')
        assert callable(getattr(graph_repo, 'cleanup_orphan_placeholders'))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
