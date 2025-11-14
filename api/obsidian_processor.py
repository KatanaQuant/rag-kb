"""
Obsidian Markdown Processor
Handles Obsidian-specific markdown syntax for RAG ingestion
"""
import re
from pathlib import Path
from typing import Dict, List, Optional
import yaml


class ObsidianFileMapper:
    """Maps note names to file paths in vault"""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.file_map: Dict[str, Path] = {}

    def build_map(self):
        """Build file mapping"""
        for md_file in self._find_markdown_files():
            if not self._should_include(md_file):
                continue
            self._add_to_map(md_file)

    def _find_markdown_files(self):
        """Find all markdown files in vault"""
        return self.vault_path.rglob("*.md")

    def _should_include(self, file_path: Path) -> bool:
        """Check if file should be included"""
        if self._is_hidden(file_path):
            return False
        if self._is_template_or_archive(file_path):
            return False
        return True

    @staticmethod
    def _is_hidden(file_path: Path) -> bool:
        """Check if path contains hidden directories"""
        return any(p.startswith('.') for p in file_path.parts)

    @staticmethod
    def _is_template_or_archive(file_path: Path) -> bool:
        """Check if in Templates or Archive"""
        parts = file_path.parts
        return 'Templates' in parts or 'Archive' in parts

    def _add_to_map(self, file_path: Path):
        """Add file to mapping"""
        note_name = file_path.stem
        rel_path = str(file_path.relative_to(self.vault_path))

        self.file_map[note_name] = file_path
        self.file_map[rel_path] = file_path

    def resolve(self, note_name: str) -> Optional[Path]:
        """Resolve note name to file path"""
        return self.file_map.get(note_name)


class FrontmatterExtractor:
    """Extracts YAML frontmatter from markdown"""

    @staticmethod
    def extract(content: str) -> tuple[Optional[Dict], str]:
        """Extract frontmatter and content"""
        pattern = r'^---\n(.*?)\n---\n'
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            return None, content

        return FrontmatterExtractor._parse_yaml(match, content)

    @staticmethod
    def _parse_yaml(match, content: str):
        """Parse YAML frontmatter"""
        try:
            fm = yaml.safe_load(match.group(1))
            clean_content = content[match.end():]
            return fm, clean_content
        except yaml.YAMLError:
            return None, content


class WikiLinkResolver:
    """Resolves Obsidian wiki-style links"""

    def __init__(self, file_mapper: ObsidianFileMapper):
        self.mapper = file_mapper

    def resolve(self, link_text: str) -> str:
        """Resolve wiki link to readable format"""
        target, display = self._parse_link(link_text)

        if self.mapper.resolve(target):
            resolved = self.mapper.resolve(target)
            return f"[{display}](→ {resolved.stem})"

        return f"[[{link_text}]]"

    @staticmethod
    def _parse_link(link: str) -> tuple[str, str]:
        """Parse link into target and display"""
        parts = link.split('|')
        target = parts[0].split('#')[0]
        display = parts[-1] if len(parts) > 1 else target
        return target, display


class SyntaxTransformer:
    """Transforms Obsidian syntax to plain markdown"""

    def __init__(self, file_mapper: ObsidianFileMapper):
        self.mapper = file_mapper
        self.link_resolver = WikiLinkResolver(file_mapper)

    def transform(self, content: str) -> str:
        """Apply all transformations"""
        content = self._remove_comments(content)
        content = self._convert_wiki_links(content)
        content = self._convert_embeds(content)
        content = self._convert_callouts(content)
        content = self._convert_dataview(content)
        content = self._convert_highlights(content)
        return content

    @staticmethod
    def _remove_comments(content: str) -> str:
        """Remove Obsidian comments %%...%%"""
        return re.sub(r'%%.*?%%', '', content, flags=re.DOTALL)

    def _convert_wiki_links(self, content: str) -> str:
        """Convert wiki-style links"""
        content = self._convert_with_display(content)
        content = self._convert_with_section(content)
        content = self._convert_simple(content)
        return content

    def _convert_with_display(self, content: str) -> str:
        """Convert [[Link|Display]]"""
        return re.sub(
            r'\[\[([^\]]+)\|([^\]]+)\]\]',
            lambda m: self._resolve_link(m.group(0)[2:-2]),
            content
        )

    def _convert_with_section(self, content: str) -> str:
        """Convert [[Link#Section]]"""
        return re.sub(
            r'\[\[([^\]]+)#([^\]]+)\]\]',
            r'[\1](→ \1 / \2)',
            content
        )

    def _convert_simple(self, content: str) -> str:
        """Convert [[Link]]"""
        return re.sub(
            r'\[\[([^\]]+)\]\]',
            lambda m: self._resolve_link(m.group(1)),
            content
        )

    def _resolve_link(self, link: str) -> str:
        """Resolve a single link"""
        return self.link_resolver.resolve(link)

    @staticmethod
    def _convert_embeds(content: str) -> str:
        """Convert Obsidian embeds ![[...]]"""
        content = SyntaxTransformer._convert_image_embeds(content)
        content = SyntaxTransformer._convert_note_embeds(content)
        return content

    @staticmethod
    def _convert_image_embeds(content: str) -> str:
        """Convert image/file embeds"""
        pattern = r'!\[\[([^\]]+\.(png|jpg|jpeg|gif|svg|pdf))\]\]'
        return re.sub(
            pattern,
            r'[Embedded file: \1]',
            content,
            flags=re.IGNORECASE
        )

    @staticmethod
    def _convert_note_embeds(content: str) -> str:
        """Convert note embeds"""
        return re.sub(
            r'!\[\[([^\]]+)\]\]',
            r'[Embedded note: \1]',
            content
        )

    @staticmethod
    def _convert_callouts(content: str) -> str:
        """Convert Obsidian callouts"""
        return re.sub(
            r'>\s*\[!(\w+)\]([+-]?)\s*([^\n]*)\n((?:>.*(?:\n|$))*)',
            SyntaxTransformer._format_callout,
            content
        )

    @staticmethod
    def _format_callout(match) -> str:
        """Format a single callout"""
        callout_type = match.group(1).upper()
        title = match.group(3)
        content = match.group(4)

        clean_content = re.sub(r'^>\s?', '', content, flags=re.MULTILINE)

        result = f"\n**{callout_type}"
        if title:
            result += f": {title}"
        result += "**\n" + clean_content

        return result

    @staticmethod
    def _convert_dataview(content: str) -> str:
        """Convert Dataview queries"""
        content = SyntaxTransformer._convert_dataview_blocks(content)
        content = SyntaxTransformer._convert_inline_dataview(content)
        return content

    @staticmethod
    def _convert_dataview_blocks(content: str) -> str:
        """Convert dataview code blocks"""
        return re.sub(
            r'```dataview\n(.*?)```',
            lambda m: f"\n[Dataview Query]\n```\n{m.group(1)}```\n",
            content,
            flags=re.DOTALL
        )

    @staticmethod
    def _convert_inline_dataview(content: str) -> str:
        """Convert inline dataview"""
        return re.sub(
            r'`\$=([^`]+)`',
            r'[Dataview: \1]',
            content
        )

    @staticmethod
    def _convert_highlights(content: str) -> str:
        """Convert ==highlight== to **bold**"""
        return re.sub(r'==([^=]+)==', r'**\1**', content)


class NoteProcessor:
    """Processes individual Obsidian notes"""

    def __init__(self, vault_path: Path, transformer: SyntaxTransformer):
        self.vault_path = vault_path
        self.transformer = transformer
        self.fm_extractor = FrontmatterExtractor()

    def process(self, file_path: Path) -> Dict:
        """Process single markdown file"""
        content = self._read_file(file_path)
        frontmatter, content = self._extract_frontmatter(content)
        content = self._transform_syntax(content)

        return self._make_result(file_path, frontmatter, content)

    @staticmethod
    def _read_file(file_path: Path) -> str:
        """Read file content"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _extract_frontmatter(self, content: str):
        """Extract frontmatter"""
        return self.fm_extractor.extract(content)

    def _transform_syntax(self, content: str) -> str:
        """Transform Obsidian syntax"""
        return self.transformer.transform(content)

    def _make_result(self, path: Path, fm: Dict, content: str) -> Dict:
        """Create result dictionary"""
        return {
            'path': str(path.relative_to(self.vault_path)),
            'name': path.stem,
            'frontmatter': fm,
            'content': content.strip()
        }


class VaultScanner:
    """Scans vault and processes all notes"""

    def __init__(self, vault_path: Path, processor: NoteProcessor):
        self.vault_path = vault_path
        self.processor = processor

    def scan(self, exclude_patterns: List[str]) -> List[Dict]:
        """Scan and process all notes"""
        results = []

        for md_file in self._find_markdown_files():
            if self._should_exclude(md_file, exclude_patterns):
                continue

            result = self._process_file(md_file)
            if result:
                results.append(result)

        return results

    def _find_markdown_files(self):
        """Find all markdown files"""
        return self.vault_path.rglob("*.md")

    def _should_exclude(self, file_path: Path, patterns: List[str]) -> bool:
        """Check if file should be excluded"""
        path_str = str(file_path).lower()
        return any(p.lower() in path_str for p in patterns)

    def _process_file(self, file_path: Path) -> Optional[Dict]:
        """Process a single file"""
        try:
            return self.processor.process(file_path)
        except Exception as e:
            print(f"Error processing file: {file_path.name}")
            return None


class VaultExporter:
    """Exports vault to markdown file"""

    def __init__(self, vault_path: Path, scanner: VaultScanner):
        self.vault_path = vault_path
        self.scanner = scanner

    def export(self, output_path: Path, exclude: List[str]) -> int:
        """Export vault to single markdown file"""
        notes = self.scanner.scan(exclude)

        with open(output_path, 'w', encoding='utf-8') as f:
            self._write_header(f, len(notes))
            self._write_notes(f, notes)

        return len(notes)

    def _write_header(self, file, note_count: int):
        """Write export header"""
        file.write("# Obsidian Vault Export\n\n")
        file.write(f"**Vault Path:** {self.vault_path}\n")
        file.write(f"**Note Count:** {note_count}\n\n")
        file.write("---\n\n")

    @staticmethod
    def _write_notes(file, notes: List[Dict]):
        """Write all notes to file"""
        for note in notes:
            VaultExporter._write_note(file, note)

    @staticmethod
    def _write_note(file, note: Dict):
        """Write single note"""
        file.write(f"## {note['name']}\n\n")
        file.write(f"**Path:** `{note['path']}`\n\n")

        if note['frontmatter']:
            VaultExporter._write_frontmatter(file, note['frontmatter'])

        file.write(note['content'])
        file.write("\n\n---\n\n")

    @staticmethod
    def _write_frontmatter(file, frontmatter: Dict):
        """Write frontmatter metadata"""
        file.write("**Metadata:**\n")
        for key, value in frontmatter.items():
            file.write(f"- {key}: {value}\n")
        file.write("\n")


class ObsidianProcessor:
    """Main facade for Obsidian vault processing"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self._setup_components()

    def _setup_components(self):
        """Initialize all components"""
        self.mapper = ObsidianFileMapper(self.vault_path)
        self.mapper.build_map()

        transformer = SyntaxTransformer(self.mapper)
        note_processor = NoteProcessor(self.vault_path, transformer)

        self.scanner = VaultScanner(self.vault_path, note_processor)
        self.exporter = VaultExporter(self.vault_path, self.scanner)

    def process_file(self, file_path: Path) -> Dict:
        """Process single file (legacy method)"""
        transformer = SyntaxTransformer(self.mapper)
        processor = NoteProcessor(self.vault_path, transformer)
        return processor.process(file_path)

    def process_vault(self, exclude: List[str] = None) -> List[Dict]:
        """Process entire vault"""
        exclude = exclude or self._default_excludes()
        return self.scanner.scan(exclude)

    @staticmethod
    def _default_excludes() -> List[str]:
        """Default exclusion patterns"""
        return ['Templates', 'Archive', '.obsidian', '.trash']

    def export_to_markdown(self, output: Path, exclude: List[str] = None):
        """Export vault to markdown file"""
        exclude = exclude or self._default_excludes()
        return self.exporter.export(output, exclude)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python obsidian_processor.py <vault_path> <output_file>")
        sys.exit(1)

    vault_path = sys.argv[1]
    output_file = sys.argv[2]

    processor = ObsidianProcessor(vault_path)
    count = processor.export_to_markdown(Path(output_file))

    print(f"✓ Processed {count} notes from {vault_path}")
    print(f"✓ Output: {output_file}")
