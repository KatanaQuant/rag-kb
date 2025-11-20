

from value_objects import IndexingStats

class CoreServices:
    """Core service dependencies

    Holds fundamental services needed throughout the application.
    Focused on storage, processing, and ML models.
    """

    def __init__(self):
        self.model = None
        self.vector_store = None
        self.processor = None
        self.progress_tracker = None

class QueryServices:
    """Query-related services

    Separated from CoreServices to maintain SRP.
    """

    def __init__(self):
        self.cache = None

class IndexingComponents:
    """Indexing queue and worker infrastructure

    Holds components for background indexing and concurrent pipeline.
    """

    def __init__(self):
        self.queue = None
        self.worker = None
        self.pipeline_coordinator = None

class RuntimeState:
    """Runtime state and statistics

    Holds mutable runtime state separate from service dependencies.
    """

    def __init__(self):
        self.watcher = None
        self.indexing_in_progress = False
        self.stats = IndexingStats()

class AppState:
    """Application state container

    Refactored to compose focused state objects instead of holding
    10+ instance variables directly.

    Benefits:
    - Easier to test individual components
    - Clear separation of concerns
    - Follows Sandi Metz < 4 instance variables rule
    """

    def __init__(self):
        self.core = CoreServices()
        self.query = QueryServices()
        self.indexing = IndexingComponents()
        self.runtime = RuntimeState()
