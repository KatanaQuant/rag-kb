"""
Configuration constants for RAG system
"""
import os
from pathlib import Path
from dataclasses import dataclass

# Model dimension mapping
MODEL_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "Snowflake/snowflake-arctic-embed-l-v2.0": 1024,
    "Snowflake/snowflake-arctic-embed-m-v2.0": 768,
    "google/embeddinggemma-300m": 768,
    "BAAI/bge-large-en-v1.5": 1024,
    "BAAI/bge-base-en-v1.5": 768,
    "sentence-transformers/static-retrieval-mrl-en-v1": 1024,  # Static embedding, 100-400x faster on CPU
}

@dataclass
class ChunkConfig:
    """Text chunking configuration"""
    size: int = 1000
    overlap: int = 200
    min_size: int = 50
    semantic: bool = True  # Use semantic chunking with Docling (HybridChunker)
    max_tokens: int = 512  # Token limit for semantic chunks

@dataclass
class DatabaseConfig:
    """Database configuration supporting PostgreSQL + pgvector (default) and SQLite + vectorlite.

    PostgreSQL fields: database_url, host, port, user, password, database
    SQLite fields (backward compatible): path, check_same_thread, require_vec_extension

    Use DatabaseFactory for runtime backend selection based on database_url prefix.
    """
    # PostgreSQL connection (from DATABASE_URL env var)
    database_url: str = ""
    # Parsed components (set from database_url)
    host: str = "localhost"
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    # Embedding configuration
    embedding_dim: int = 384
    # Legacy SQLite path (for migration only)
    sqlite_path: str = "/app/data/rag.db"

    # ============================================================
    # SQLite backward compatibility (deprecated, for tests/migration)
    # ============================================================
    path: str = "/app/data/rag.db"  # SQLite database file path
    check_same_thread: bool = False  # SQLite threading mode
    require_vec_extension: bool = False  # Whether vectorlite extension is required
    validate_hnsw: bool = True  # Whether to validate HNSW index size (disable for tests)

    @classmethod
    def from_url(cls, url: str, embedding_dim: int = 384) -> 'DatabaseConfig':
        """Parse DATABASE_URL and create config.

        Supports:
        - postgresql://user:pass@host:port/dbname
        - sqlite:///path/to/db.sqlite
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)

        if url.startswith('sqlite'):
            # SQLite URL: sqlite:///path/to/db.sqlite
            sqlite_path = parsed.path or "/app/data/rag.db"
            return cls(
                database_url=url,
                sqlite_path=sqlite_path,
                path=sqlite_path,  # backward compat
                embedding_dim=embedding_dim,
            )
        else:
            # PostgreSQL URL
            return cls(
                database_url=url,
                host=parsed.hostname or "localhost",
                port=parsed.port or 5432,
                user=parsed.username or "",
                password=parsed.password or "",
                database=parsed.path.lstrip('/') or "",
                embedding_dim=embedding_dim,
            )

@dataclass
class ModelConfig:
    """Embedding model configuration"""
    name: str = "sentence-transformers/all-MiniLM-L6-v2"
    show_progress: bool = False

    def get_embedding_dim(self) -> int:
        """Get embedding dimension for configured model"""
        return MODEL_DIMENSIONS.get(self.name, 384)

@dataclass
class PathConfig:
    """File path configuration"""
    knowledge_base: Path = Path("/app/kb")
    data_dir: Path = Path("/app/data")

@dataclass
class WatcherConfig:
    """File watcher configuration"""
    enabled: bool = True
    debounce_seconds: float = 10.0
    batch_size: int = 50

@dataclass
class CacheConfig:
    """Query cache configuration"""
    enabled: bool = True
    max_size: int = 100

@dataclass
class BatchConfig:
    """Batch processing configuration for resource management"""
    size: int = 5
    delay: float = 0.5

@dataclass
class DoclingConfig:
    """Docling PDF extraction configuration"""
    enabled: bool = True  # Default to advanced PDF extraction
    generate_page_images: bool = True  # Generate page images (set False for ~20-30% memory savings)
    generate_picture_images: bool = True  # Generate picture images (set False for ~10-20% memory savings)
    pdf_backend: str = "dlparse_v4"  # PDF backend: dlparse_v4 (default) or pypdfium2 (~80% less memory)

@dataclass
class ProcessingConfig:
    """Resumable processing configuration"""
    enabled: bool = True
    batch_size: int = 50
    max_retries: int = 3
    cleanup_completed: bool = False

@dataclass
class FileValidationConfig:
    """File type validation configuration"""
    enabled: bool = True
    action: str = "reject"  # reject|warn|skip (changed from warn in v1.3.0 for security)

@dataclass
class MalwareDetectionConfig:
    """Advanced malware detection configuration

    Severity tiers:
    - CRITICAL: ClamAV + Hash blacklist (auto-quarantine)
    - WARNING: YARA rules (logged, user decides)
    """
    clamav_enabled: bool = True  # Enabled by default (standalone in container)
    clamav_socket: str = "/var/run/clamav/clamd.ctl"
    hash_blacklist_enabled: bool = True  # Enabled by default with curated list
    hash_blacklist_path: str = "/app/data/malware_hashes.txt"
    yara_enabled: bool = True  # Enabled by default with document-focused rules
    yara_rules_path: str = "/app/yara_config/yara_rules.yar"
    # Allowlist for known-safe files (skip all security checks)
    allowlist_path: str = "/app/data/security_allowlist.txt"
    # YARA rules produce warnings by default (not blocks)
    yara_warning_only: bool = True

@dataclass
class Config:
    """Main configuration container"""
    chunks: ChunkConfig
    database: DatabaseConfig
    model: ModelConfig
    paths: PathConfig
    watcher: WatcherConfig
    cache: CacheConfig
    batch: BatchConfig
    docling: DoclingConfig
    processing: ProcessingConfig
    file_validation: FileValidationConfig
    malware_detection: MalwareDetectionConfig

    @classmethod
    def from_env(cls) -> 'Config':
        """Create config from environment - delegates to EnvironmentConfigLoader"""
        from environment_config_loader import EnvironmentConfigLoader
        return EnvironmentConfigLoader().load()

# Default instance
default_config = Config.from_env()
