"""Obsidian Vault Detection

Detects if a markdown file is part of an Obsidian vault.
Uses heuristics: .obsidian folder, wikilinks, tags, frontmatter.
"""

from pathlib import Path
import re

class ObsidianDetector:
    """Detects Obsidian vaults and notes

    Small, focused class following Sandi Metz principles.
    """

    def __init__(self):
        self.wikilink_pattern = re.compile(r'\[\[([^\]]+)\]\]')
        self.tag_pattern = re.compile(r'#[\w/\-]+')
        self.frontmatter_pattern = re.compile(r'^---\n.+?\n---', re.DOTALL)

    def is_obsidian_vault(self, path: Path) -> bool:
        """Check if path is within an Obsidian vault

        Args:
            path: File or directory path

        Returns:
            True if .obsidian folder exists in path hierarchy
        """
        current = path if path.is_dir() else path.parent

        # Walk up directory tree looking for .obsidian
        while current != current.parent:
            obsidian_dir = current / '.obsidian'
            if obsidian_dir.exists() and obsidian_dir.is_dir():
                return True
            current = current.parent

        return False

    def is_obsidian_note(self, path: Path) -> bool:
        """Check if markdown file is an Obsidian note

        Uses multiple heuristics:
        1. Is in vault (has .obsidian in hierarchy)
        2. Contains wikilinks [[like this]]
        3. Contains tags #like-this
        4. Has YAML frontmatter

        Note: Even one indicator is enough to classify as Obsidian note
        """
        if not path.suffix.lower() in ['.md', '.markdown']:
            return False

        # First check: In Obsidian vault?
        if self.is_obsidian_vault(path):
            return True

        # Second check: File content has Obsidian features?
        return self._has_obsidian_features(path)

    def _has_obsidian_features(self, path: Path) -> bool:
        """Check file content for Obsidian features"""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first 1000 chars (enough for detection)
                content = f.read(1000)

            # Check for wikilinks
            if self.wikilink_pattern.search(content):
                return True

            # Check for tags (at least 2 to avoid false positives)
            tags = self.tag_pattern.findall(content)
            if len(tags) >= 2:
                return True

            # Check for frontmatter
            if self.frontmatter_pattern.match(content):
                return True

            return False

        except Exception:
            return False

# Global singleton
_detector = None

def get_obsidian_detector() -> ObsidianDetector:
    """Get or create singleton detector"""
    global _detector
    if _detector is None:
        _detector = ObsidianDetector()
    return _detector
