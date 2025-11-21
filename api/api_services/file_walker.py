from pathlib import Path
from ingestion.file_filter import FileFilterPolicy


class FileWalker:
    """Walks knowledge base directory

    Refactored following Sandi Metz principles:
    - Dependency Injection: filter_policy injected vs. hardcoded
    - Single Responsibility: Only handles directory walking
    - Small class: Reduced from ~70 lines to ~20 lines
    """

    def __init__(self, base_path: Path, extensions: set, filter_policy: FileFilterPolicy = None):
        self.base_path = base_path
        self.extensions = extensions
        self.filter_policy = filter_policy or FileFilterPolicy()

    def walk(self):
        """Yield supported files"""
        if not self.base_path.exists():
            return
        yield from self._walk_files()

    def _walk_files(self):
        """Walk all files"""
        for file_path in self.base_path.rglob("*"):
            if self._is_supported(file_path) and not self.filter_policy.should_exclude(file_path):
                yield file_path

    def _is_supported(self, path: Path) -> bool:
        """Check if file is supported"""
        if not path.is_file():
            return False
        return path.suffix.lower() in self.extensions
