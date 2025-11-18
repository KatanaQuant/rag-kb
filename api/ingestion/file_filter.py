"""File filtering policy - extracted from FileWalker for SRP compliance

Following Sandi Metz principles:
- Single Responsibility: Only handles file exclusion logic
- Small methods: Each method under 5 lines where possible
- Tell, Don't Ask: Policy makes decisions, doesn't expose internals
"""
from pathlib import Path
from typing import Set


class FileFilterPolicy:
    """Determines which files should be excluded from processing

    Follows Sandi Metz SRP: This class has one reason to change -
    when exclusion rules need to be updated.
    """

    # Class-level constants for excluded patterns
    EXCLUDED_DIRS = {
        '.git', '.svn', '.hg',  # Version control
        'node_modules', '__pycache__', '.pytest_cache',  # Dependencies & cache
        '.venv', 'venv', 'env', '.env',  # Virtual environments
        'dist', 'build', '.eggs', '*.egg-info',  # Build artifacts
        '.cache', '.mypy_cache', '.ruff_cache',  # Tool caches
        'target', 'bin', 'obj',  # Compiled outputs (Java, C#, etc)
        '.idea', '.vscode', '.vs',  # IDE directories
        'coverage', 'htmlcov', '.coverage',  # Test coverage
    }

    EXCLUDED_FILE_PATTERNS = [
        '.env', '.env.local', '.env.production',  # Environment files
        'secrets', 'credentials',  # Secret files
        '.ds_store', 'thumbs.db',  # OS artifacts (lowercase for matching)
        '*.pyc', '*.pyo', '*.pyd',  # Python compiled
        '*.so', '*.dylib', '*.dll',  # Shared libraries
        '*.class', '*.jar', '*.war',  # Java compiled
        '*.min.js', '*.min.css',  # Minified assets
    ]

    EXCLUDED_SUBDIRS = {'problematic', 'original'}
    TEMP_PDF_PATTERNS = {'.tmp.pdf', '.gs_tmp.pdf'}

    def should_exclude(self, path: Path) -> bool:
        """Determine if file should be excluded

        Following Sandi Metz: Public interface is simple, implementation hidden.
        Returns boolean - caller doesn't need to know WHY file is excluded.
        """
        return (
            self._is_in_excluded_subdir(path) or
            self._is_temp_file(path) or
            self._is_in_excluded_directory(path) or
            self._matches_excluded_pattern(path)
        )

    def _is_in_excluded_subdir(self, path: Path) -> bool:
        """Check if path contains excluded subdirectories"""
        return any(part in self.EXCLUDED_SUBDIRS for part in path.parts)

    def _is_temp_file(self, path: Path) -> bool:
        """Check if file is temporary processing artifact"""
        return any(pattern in path.name for pattern in self.TEMP_PDF_PATTERNS)

    def _is_in_excluded_directory(self, path: Path) -> bool:
        """Check if any part of path is in excluded directories"""
        for part in path.parts:
            if self._is_excluded_part(part):
                return True
        return False

    def _is_excluded_part(self, part: str) -> bool:
        """Check if single path part should be excluded"""
        if part in self.EXCLUDED_DIRS:
            return True
        # Exclude hidden files/dirs (starting with .) except '..'
        if part.startswith('.') and part != '..':
            return True
        return False

    def _matches_excluded_pattern(self, path: Path) -> bool:
        """Check if filename matches any excluded patterns"""
        filename_lower = path.name.lower()

        for pattern in self.EXCLUDED_FILE_PATTERNS:
            if self._pattern_matches(filename_lower, pattern):
                return True
        return False

    def _pattern_matches(self, filename: str, pattern: str) -> bool:
        """Check if filename matches pattern

        Following Sandi Metz: Small, focused method doing one thing.
        """
        if pattern.startswith('*'):
            return filename.endswith(pattern[1:])
        return pattern in filename
