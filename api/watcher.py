"""
File system watcher for automatic document indexing
"""
import threading
import time
from pathlib import Path
from typing import Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

class DebounceTimer:
    """Manages debounce timing for file events"""

    def __init__(self, delay: float, callback: Callable):
        self.delay = delay
        self.callback = callback
        self.timer: Optional[threading.Timer] = None
        self.lock = threading.Lock()

    def trigger(self):
        """Trigger or reset the timer"""
        with self.lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.delay, self._execute)
            self.timer.start()

    def _execute(self):
        """Execute callback after delay"""
        self.callback()

    def cancel(self):
        """Cancel pending timer"""
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None

class FileChangeCollector:
    """Collects and deduplicates file change events"""

    def __init__(self):
        self.changed_files: Set[Path] = set()
        self.lock = threading.Lock()

    def add(self, file_path: Path):
        """Add a changed file"""
        with self.lock:
            self.changed_files.add(file_path)

    def get_and_clear(self) -> Set[Path]:
        """Get all changes and clear collection"""
        with self.lock:
            files = self.changed_files.copy()
            self.changed_files.clear()
            return files

    def count(self) -> int:
        """Get count of pending changes"""
        with self.lock:
            return len(self.changed_files)

class DocumentEventHandler(FileSystemEventHandler):
    """Handles file system events for documents"""

    SUPPORTED_EXTENSIONS = {
        # Documents
        '.pdf', '.md', '.txt', '.docx', '.epub', '.markdown',
        # Code files
        '.py', '.java', '.ts', '.tsx', '.js', '.jsx', '.cs',
        # Jupyter notebooks
        '.ipynb'
    }

    def __init__(self, collector: FileChangeCollector, timer: DebounceTimer):
        self.collector = collector
        self.timer = timer
        super().__init__()

    def on_created(self, event: FileSystemEvent):
        """Handle file creation"""
        if not event.is_directory:
            self._handle_change(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification"""
        if not event.is_directory:
            self._handle_change(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion"""
        # For deletions, we might want to remove from DB
        # For now, just skip - change detection will handle it
        pass

    def _handle_change(self, file_path: str):
        """Process file change event"""
        path = Path(file_path)
        if self._is_supported(path) and not self._is_excluded(path):
            self.collector.add(path)
            self.timer.trigger()

    def _is_supported(self, path: Path) -> bool:
        """Check if file type is supported"""
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def _is_excluded(self, path: Path) -> bool:
        """Check if file path should be excluded from processing"""
        # Exclude files in 'problematic' and 'original' subdirectories
        if 'problematic' in path.parts or 'original' in path.parts:
            return True
        # Exclude temporary files created during processing
        if '.tmp.pdf' in path.name or '.gs_tmp.pdf' in path.name:
            return True
        return False

class IndexingCoordinator:
    """Coordinates the indexing process via queue

    Routes all file changes through IndexingQueue for concurrent pipeline processing.
    """

    def __init__(self, queue, collector: FileChangeCollector, batch_size: int):
        self.queue = queue
        self.collector = collector
        self.batch_size = batch_size

    def process_changes(self):
        """Add all collected file changes to queue for processing"""
        files = self.collector.get_and_clear()
        if not files:
            return

        print(f"Queueing {len(files)} changed file(s) for processing")
        self._queue_files(files)

    def _queue_files(self, files: Set[Path]):
        """Add files to indexing queue"""
        from services import Priority

        files_list = list(files)[:self.batch_size]

        queued_count = 0
        for file_path in files_list:
            try:
                self.queue.add(file_path, priority=Priority.NORMAL, force=False)
                queued_count += 1
                print(f"  Queued: {file_path.name}")
            except Exception as e:
                print(f"  ✗ Failed to queue {file_path.name}: {e}")

        print(f"Queued {queued_count} file(s) for concurrent pipeline processing")

class FileWatcherService:
    """Main file watcher service - routes files to queue"""

    def __init__(self, watch_path: Path, queue, debounce_seconds: float, batch_size: int):
        self.watch_path = watch_path
        self.collector = FileChangeCollector()
        self.coordinator = IndexingCoordinator(queue, self.collector, batch_size)
        self.timer = DebounceTimer(debounce_seconds, self._on_debounce)
        self.handler = DocumentEventHandler(self.collector, self.timer)
        self.observer: Optional[Observer] = None

    def _on_debounce(self):
        """Called after debounce period"""
        try:
            self.coordinator.process_changes()
        except Exception as e:
            print("Error during indexing")

    def start(self):
        """Start watching for file changes"""
        if not self.watch_path.exists():
            print("Warning: Watch path does not exist")
            return

        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.watch_path), recursive=True)
        self.observer.start()
        print("File watcher started")

    def stop(self):
        """Stop watching for file changes"""
        if self.observer:
            self.timer.cancel()
            self.observer.stop()
            self.observer.join(timeout=5)
            print("File watcher stopped")
