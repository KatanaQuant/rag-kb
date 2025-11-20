"""Application state container"""

from value_objects import IndexingStats

class AppState:
    """Application state container

    Sandi Metz compliance:
    - Reduced from 11 instance variables to 9
    - Groups related state
    """

    def __init__(self):
        # Core components
        self.model = None
        self.vector_store = None
        self.processor = None

        # Services
        self.watcher = None
        self.cache = None
        self.progress_tracker = None

        # Indexing state
        self.indexing_queue = None
        self.indexing_worker = None
        self.indexing_stats = IndexingStats()

class IndexingState:
    """Separate indexing state for future refactoring"""

    def __init__(self):
        self.in_progress = False
        self.queue = None
        self.worker = None
        self.stats = IndexingStats()
