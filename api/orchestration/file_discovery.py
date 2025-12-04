"""File discovery and categorization for indexing"""

from pathlib import Path
from typing import List
from collections import defaultdict

class FileDiscovery:
    """Discovers and categorizes files for display

    Design principles:
    - Single responsibility: file discovery and categorization
    - Small methods (< 5 lines each)
    """

    def group_for_display(self, files: List[Path]) -> str:
        """Group files by directory for cleaner display"""
        root_pdfs, dir_groups = self._categorize(files)
        return self._build_display(root_pdfs, dir_groups)

    def _categorize(self, files: List[Path]) -> tuple:
        """Categorize files into root PDFs and directory groups"""
        root_pdfs = []
        dir_groups = defaultdict(list)
        for file_path in files:
            self._categorize_one(file_path, root_pdfs, dir_groups)
        return root_pdfs, dir_groups

    def _categorize_one(self, file_path: Path, root_pdfs: List, dir_groups: dict):
        """Categorize a single file"""
        parts = file_path.parts
        kb_index = self._find_kb_index(parts)
        if self._is_subdir_file(kb_index, parts):
            self._add_to_subdir(file_path, parts, kb_index, dir_groups)
        elif file_path.suffix == '.pdf':
            root_pdfs.append(file_path)

    def _find_kb_index(self, parts: tuple) -> int:
        """Find knowledge_base index in path parts"""
        return parts.index('knowledge_base') if 'knowledge_base' in parts else -1

    def _is_subdir_file(self, kb_index: int, parts: tuple) -> bool:
        """Check if file is in a subdirectory"""
        return kb_index >= 0 and kb_index + 2 < len(parts)

    def _add_to_subdir(self, file_path: Path, parts: tuple, kb_index: int, dir_groups: dict):
        """Add file to subdirectory group"""
        subdir = parts[kb_index + 1]
        dir_groups[subdir].append(file_path)

    def _build_display(self, root_pdfs: List, dir_groups: dict) -> str:
        """Build display string from categorized files"""
        lines = []
        self._add_root_pdfs(root_pdfs, lines)
        self._add_directories(root_pdfs, dir_groups, lines)
        return "\n".join(lines)

    def _add_root_pdfs(self, root_pdfs: List, lines: List):
        """Add root PDFs to display"""
        if root_pdfs:
            lines.extend(self._format_root_pdfs(root_pdfs))

    def _add_directories(self, root_pdfs: List, dir_groups: dict, lines: List):
        """Add directory groups to display"""
        if dir_groups:
            if root_pdfs:
                lines.append("")
            lines.extend(self._format_directories(dir_groups))

    def _format_root_pdfs(self, root_pdfs: List) -> List[str]:
        """Format root PDF list"""
        lines = ["PDFs:"]
        for pdf in sorted(root_pdfs):
            lines.append(f"  - {pdf.name}")
        return lines

    def _format_directories(self, dir_groups: dict) -> List[str]:
        """Format directory groups"""
        lines = ["Directories:"]
        for dir_name, files in sorted(dir_groups.items(), key=lambda x: -len(x[1])):
            lines.append(f"  - {dir_name}/ ({len(files)} files)")
        return lines
