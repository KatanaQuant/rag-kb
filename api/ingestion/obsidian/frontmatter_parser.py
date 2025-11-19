"""Frontmatter parser - extracted from ObsidianExtractor

POODR Phase 2.2: God Class Decomposition
- Extracted from ObsidianExtractor
- Single Responsibility: Parse YAML frontmatter from markdown
- Reduces ObsidianExtractor complexity
"""

import re
import yaml
from typing import Optional, Dict


class FrontmatterParser:
    """Parse YAML frontmatter from markdown files

    Single Responsibility: Extract and parse frontmatter

    Handles YAML frontmatter blocks (--- ... ---) at start of markdown files.
    Common in Obsidian notes for metadata.
    """

    def __init__(self):
        """Initialize parser with frontmatter regex"""
        self.frontmatter_pattern = re.compile(r'^---\n(.+?)\n---\n', re.DOTALL)

    def extract_frontmatter(self, content: str) -> Optional[Dict]:
        """Extract YAML frontmatter from content

        Args:
            content: Markdown content with potential frontmatter

        Returns:
            Dict of frontmatter data, or None if not present/invalid
        """
        match = self.frontmatter_pattern.match(content)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))
        except:
            return None

    def remove_frontmatter(self, content: str) -> str:
        """Remove frontmatter from content

        Args:
            content: Markdown content with potential frontmatter

        Returns:
            Content without frontmatter block
        """
        return self.frontmatter_pattern.sub('', content)
