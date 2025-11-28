"""Tests for FrontmatterParser

Unit tests for YAML frontmatter extraction from markdown files.
"""

import pytest
from ingestion.obsidian.frontmatter_parser import FrontmatterParser


class TestFrontmatterExtraction:
    """Test frontmatter extraction"""

    @pytest.fixture
    def parser(self):
        return FrontmatterParser()

    def test_extract_simple_frontmatter(self, parser):
        """Extract basic YAML frontmatter"""
        content = """---
title: My Note
tags: [python, testing]
---
# Content starts here
"""
        result = parser.extract_frontmatter(content)

        assert result is not None
        assert result['title'] == 'My Note'
        assert result['tags'] == ['python', 'testing']

    def test_extract_frontmatter_with_nested_values(self, parser):
        """Extract frontmatter with nested YAML"""
        content = """---
metadata:
  author: Test Author
  version: "1.0.0"
---
Content here
"""
        result = parser.extract_frontmatter(content)

        assert result is not None
        assert result['metadata']['author'] == 'Test Author'
        assert result['metadata']['version'] == '1.0.0'

    def test_extract_frontmatter_empty_values(self, parser):
        """Handle frontmatter with empty values"""
        content = """---
title:
tags: []
---
Content
"""
        result = parser.extract_frontmatter(content)

        assert result is not None
        assert result['title'] is None
        assert result['tags'] == []

    def test_no_frontmatter_returns_none(self, parser):
        """Return None when no frontmatter present"""
        content = """# Just a heading

Some content without frontmatter.
"""
        result = parser.extract_frontmatter(content)

        assert result is None

    def test_frontmatter_not_at_start_returns_none(self, parser):
        """Frontmatter must be at the very start"""
        content = """Some text first

---
title: Late Frontmatter
---
"""
        result = parser.extract_frontmatter(content)

        assert result is None

    def test_invalid_yaml_returns_none(self, parser):
        """Invalid YAML gracefully returns None"""
        content = """---
title: [unclosed bracket
invalid: yaml: here
---
Content
"""
        result = parser.extract_frontmatter(content)

        assert result is None

    def test_frontmatter_with_multiline_string(self, parser):
        """Handle multiline string values"""
        content = """---
description: |
  This is a long description
  that spans multiple lines.
---
Content
"""
        result = parser.extract_frontmatter(content)

        assert result is not None
        assert 'multiple lines' in result['description']

    def test_frontmatter_boolean_values(self, parser):
        """Handle boolean values"""
        content = """---
draft: true
published: false
---
Content
"""
        result = parser.extract_frontmatter(content)

        assert result is not None
        assert result['draft'] is True
        assert result['published'] is False


class TestFrontmatterRemoval:
    """Test frontmatter removal from content"""

    @pytest.fixture
    def parser(self):
        return FrontmatterParser()

    def test_remove_frontmatter(self, parser):
        """Remove frontmatter from content"""
        content = """---
title: Test
---
# Heading

Body content.
"""
        result = parser.remove_frontmatter(content)

        assert '---' not in result
        assert 'title: Test' not in result
        assert '# Heading' in result
        assert 'Body content.' in result

    def test_remove_frontmatter_preserves_content(self, parser):
        """Content after frontmatter is preserved exactly"""
        content = """---
tags: [test]
---
Line 1
Line 2
Line 3
"""
        result = parser.remove_frontmatter(content)

        assert result == "Line 1\nLine 2\nLine 3\n"

    def test_remove_frontmatter_no_frontmatter(self, parser):
        """Content without frontmatter returned unchanged"""
        content = """# No frontmatter

Just content.
"""
        result = parser.remove_frontmatter(content)

        assert result == content

    def test_remove_frontmatter_empty_content_after(self, parser):
        """Handle frontmatter-only files"""
        content = """---
title: Only Metadata
---
"""
        result = parser.remove_frontmatter(content)

        assert result == ""


class TestEdgeCases:
    """Test edge cases"""

    @pytest.fixture
    def parser(self):
        return FrontmatterParser()

    def test_empty_string(self, parser):
        """Handle empty input"""
        assert parser.extract_frontmatter("") is None
        assert parser.remove_frontmatter("") == ""

    def test_only_dashes(self, parser):
        """Handle malformed frontmatter markers"""
        content = "---\n---\n"
        result = parser.extract_frontmatter(content)
        # Empty YAML is valid and returns None (yaml.safe_load returns None for empty)
        assert result is None

    def test_single_dash_separator(self, parser):
        """Require exactly three dashes"""
        content = """--
title: Wrong
--
Content
"""
        result = parser.extract_frontmatter(content)

        assert result is None

    def test_frontmatter_with_horizontal_rule_in_content(self, parser):
        """Don't confuse horizontal rules with frontmatter end"""
        content = """---
title: Test
---
Content

---

More content after rule.
"""
        result = parser.remove_frontmatter(content)

        assert 'Content' in result
        assert '---' in result  # HR preserved
        assert 'More content' in result

    def test_unicode_in_frontmatter(self, parser):
        """Handle unicode characters"""
        content = """---
title: "Notes sur l'architecture"
emoji: "notes"
---
Content
"""
        result = parser.extract_frontmatter(content)

        assert result is not None
        assert "l'architecture" in result['title']
