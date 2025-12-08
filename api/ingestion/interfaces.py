"""
Database abstraction layer interfaces.

These ABCs define the contract that all database implementations must follow.
This enables:
- Easy switching between PostgreSQL, SQLite, or other backends
- Runtime database selection via factory pattern
- Backend-agnostic testing with mock implementations

Usage:
    from ingestion.interfaces import VectorStore, DatabaseConnection
    from ingestion.database_factory import DatabaseFactory

    store = DatabaseFactory.create_vector_store(config)  # Returns implementation
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, Any


@dataclass
class SearchResult:
    """Unified search result returned by all VectorStore implementations.

    This ensures consistent result format regardless of backend.

    Attributes:
        chunk_id: Unique identifier for the chunk in the database.
        content: The text content of the chunk.
        file_path: Full path to the source document.
        page: Page number if available (e.g., from PDF), None otherwise.
        score: Similarity score (0-1, higher = more similar).
        source: Filename extracted from file_path for QueryExecutor compatibility.
        filename: Legacy alias for source, maintained for backward compatibility.
    """
    chunk_id: int
    content: str
    file_path: str
    page: Optional[int]
    score: float
    source: str  # filename for QueryExecutor compatibility
    filename: str  # legacy alias

    @classmethod
    def from_dict(cls, data: Dict) -> 'SearchResult':
        """Create SearchResult from dictionary (e.g., repository output).

        Args:
            data: Dictionary with chunk_id, content, file_path, page, score keys.
                  source/filename are derived from file_path if not present.

        Returns:
            SearchResult instance.
        """
        from pathlib import Path
        file_path = data.get('file_path', '')
        filename = Path(file_path).name if file_path else ''

        return cls(
            chunk_id=data.get('chunk_id', 0),
            content=data.get('content', ''),
            file_path=file_path,
            page=data.get('page'),
            score=data.get('score', 0.0),
            source=data.get('source', filename),
            filename=data.get('filename', filename),
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses.

        Returns:
            Dictionary representation compatible with existing API contracts.
        """
        return {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'file_path': self.file_path,
            'page': self.page,
            'score': self.score,
            'source': self.source,
            'filename': self.filename,
        }


class DatabaseConnection(ABC):
    """Abstract database connection interface.

    Implementations handle connection lifecycle and extension setup.
    Each backend has different requirements:
    - PostgreSQL: psycopg2 connection with pgvector extension
    - SQLite: sqlite3 connection with vectorlite extension

    Example:
        conn = PostgresConnection(config)
        db = conn.connect()
        # ... use db ...
        conn.close()
    """

    @abstractmethod
    def connect(self) -> Any:
        """Establish database connection and return connection object.

        Should also initialize any required extensions (pgvector, vectorlite).

        Returns:
            Database connection object (psycopg2.connection or sqlite3.Connection).

        Raises:
            RuntimeError: If connection fails or required extensions unavailable.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close database connection and release resources.

        For SQLite/vectorlite, this persists the HNSW index.
        For PostgreSQL, this is a simple connection close.
        """
        pass


class SchemaManager(ABC):
    """Abstract schema manager interface.

    Implementations create database-specific schemas including:
    - documents: File metadata
    - chunks: Text chunks with page info
    - vec_chunks: Vector embeddings (pgvector or vectorlite)
    - fts_chunks: Full-text search (tsvector or FTS5)
    - graph tables: Knowledge graph for Graph-RAG
    - processing_progress: Resume support
    - security_scan_cache: Malware scan results
    """

    @abstractmethod
    def create_schema(self) -> None:
        """Create all required tables and indexes.

        Should be idempotent - safe to call multiple times.
        Uses CREATE TABLE IF NOT EXISTS pattern.
        """
        pass


class DocumentRepository(ABC):
    """Abstract document repository interface.

    Handles CRUD operations for the documents table.
    Documents represent indexed files with their metadata.
    """

    @abstractmethod
    def add(self, path: str, hash_val: str, extraction_method: str = None) -> int:
        """Add document and return ID.

        Args:
            path: Full file path to the document.
            hash_val: SHA256 hash of file content for deduplication.
            extraction_method: Extraction method used (e.g., 'docling', 'pypdf').

        Returns:
            Integer document ID from database.
        """
        pass

    @abstractmethod
    def get(self, doc_id: int) -> Optional[Dict]:
        """Get document by ID.

        Args:
            doc_id: Document ID to retrieve.

        Returns:
            Dictionary with id, file_path, file_hash, indexed_at, extraction_method
            or None if not found.
        """
        pass

    @abstractmethod
    def find_by_path(self, path: str) -> Optional[Dict]:
        """Find document by file path.

        Args:
            path: Full file path to search for.

        Returns:
            Document dictionary or None if not found.
        """
        pass

    @abstractmethod
    def find_by_hash(self, hash_val: str) -> Optional[Dict]:
        """Find document by content hash.

        Useful for detecting file moves - same content, different path.

        Args:
            hash_val: SHA256 hash of file content.

        Returns:
            Document dictionary or None if not found.
        """
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if document exists by path.

        Args:
            path: Full file path to check.

        Returns:
            True if document exists, False otherwise.
        """
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete document by path.

        CASCADE should delete associated chunks, vectors, and FTS entries.

        Args:
            path: Full file path of document to delete.
        """
        pass

    @abstractmethod
    def delete_by_id(self, doc_id: int) -> None:
        """Delete document by ID.

        CASCADE should delete associated chunks, vectors, and FTS entries.

        Args:
            doc_id: Document ID to delete.
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Count total documents.

        Returns:
            Integer count of documents in database.
        """
        pass

    @abstractmethod
    def list_all(self) -> List[Dict]:
        """Get all documents.

        Returns:
            List of document dictionaries with all metadata.
        """
        pass


class ChunkRepository(ABC):
    """Abstract chunk repository interface.

    Handles CRUD operations for text chunks.
    Chunks are portions of documents that get embedded for search.
    """

    @abstractmethod
    def add(self, document_id: int, content: str, page: int = None, chunk_index: int = None) -> int:
        """Insert chunk and return chunk ID.

        Args:
            document_id: Parent document ID (foreign key).
            content: Text content of the chunk.
            page: Page number if from paginated document (e.g., PDF).
            chunk_index: Position of chunk within document for ordering.

        Returns:
            Integer chunk ID from database.
        """
        pass

    @abstractmethod
    def get(self, chunk_id: int) -> Optional[Dict]:
        """Get chunk by ID.

        Args:
            chunk_id: Chunk ID to retrieve.

        Returns:
            Dictionary with id, document_id, content, page, chunk_index
            or None if not found.
        """
        pass

    @abstractmethod
    def get_by_document(self, document_id: int) -> List[Dict]:
        """Get all chunks for a document.

        Args:
            document_id: Document ID to get chunks for.

        Returns:
            List of chunk dictionaries ordered by chunk_index.
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Count total chunks.

        Returns:
            Integer count of chunks across all documents.
        """
        pass

    @abstractmethod
    def count_by_document(self, document_id: int) -> int:
        """Count chunks for a specific document.

        Args:
            document_id: Document ID to count chunks for.

        Returns:
            Integer count of chunks for the document.
        """
        pass


class VectorChunkRepository(ABC):
    """Abstract vector embeddings repository interface.

    Stores vector embeddings for semantic search.
    Backend implementations:
    - PostgreSQL: pgvector extension with HNSW index
    - SQLite: vectorlite extension with HNSW index
    """

    @abstractmethod
    def add(self, chunk_id: int, embedding: List[float]) -> None:
        """Insert vector embedding for a chunk.

        Args:
            chunk_id: Chunk ID this embedding belongs to.
            embedding: List of floats representing the embedding vector.
        """
        pass

    @abstractmethod
    def add_batch(self, chunk_ids: List[int], embeddings: List[List[float]]) -> None:
        """Batch insert vector embeddings.

        More efficient than individual inserts for bulk operations.

        Args:
            chunk_ids: List of chunk IDs.
            embeddings: List of embedding vectors (same length as chunk_ids).
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Count total vector embeddings.

        Returns:
            Integer count of embeddings in the vector index.
        """
        pass


class FTSChunkRepository(ABC):
    """Abstract full-text search repository interface.

    Provides keyword-based search complementing vector similarity.
    Backend implementations:
    - PostgreSQL: tsvector with GIN index
    - SQLite: FTS5 virtual table
    """

    @abstractmethod
    def add(self, chunk_id: int, content: str) -> None:
        """Insert FTS entry for a chunk.

        Args:
            chunk_id: Chunk ID this FTS entry belongs to.
            content: Text content to index for full-text search.
        """
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search using full-text search.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of dictionaries with chunk_id and rank/score.
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Count total FTS entries.

        Returns:
            Integer count of FTS-indexed chunks.
        """
        pass


class SearchRepository(ABC):
    """Abstract vector similarity search interface.

    Performs approximate nearest neighbor search using HNSW index.
    This is the core search operation for semantic retrieval.
    """

    @abstractmethod
    def vector_search(self, embedding: List[float], top_k: int,
                      threshold: float = None) -> List[Dict]:
        """Search for similar vectors.

        Args:
            embedding: Query vector to find similar chunks for.
            top_k: Maximum number of results to return.
            threshold: Optional similarity threshold (0-1).
                      Results below threshold are filtered out.

        Returns:
            List of dictionaries with chunk_id, content, file_path, page, score,
            source (filename), filename (legacy alias).
        """
        pass


class VectorStore(ABC):
    """High-level vector store facade interface.

    This is the main interface applications should use.
    Implementations coordinate repositories and provide:
    - Thread safety via locks
    - Hybrid search (vector + FTS)
    - Document lifecycle management
    - Statistics and monitoring

    Example:
        store = DatabaseFactory.create_vector_store(config)

        # Check if document needs indexing
        if not store.is_document_indexed(path, hash_val):
            store.add_document(path, hash_val, chunks, embeddings)

        # Search
        results = store.search(query_embedding, top_k=5, query_text="search terms")

        # Cleanup
        store.close()
    """

    @abstractmethod
    def is_document_indexed(self, path: str, hash_val: str) -> bool:
        """Check if document is indexed.

        Uses hash to detect file moves - if hash matches but path differs,
        the path is updated without re-indexing.

        Args:
            path: Current file path.
            hash_val: SHA256 hash of file content.

        Returns:
            True if document is indexed (by hash), False otherwise.
        """
        pass

    @abstractmethod
    def add_document(self, file_path: str, file_hash: str,
                     chunks: List[Dict], embeddings: List) -> None:
        """Add document with chunks and embeddings.

        If document already exists at path, it is replaced.

        Args:
            file_path: Full path to the document.
            file_hash: SHA256 hash of file content.
            chunks: List of chunk dictionaries with 'content', 'page' keys.
                   May include '_extraction_method' in first chunk.
            embeddings: List of embedding vectors (same length as chunks).
        """
        pass

    @abstractmethod
    def search(self, query_embedding: List, top_k: int = 5,
               threshold: float = None, query_text: Optional[str] = None,
               use_hybrid: bool = True) -> List[Dict]:
        """Search for similar chunks.

        Performs vector similarity search, optionally combined with
        full-text search for hybrid retrieval.

        Args:
            query_embedding: Query vector from embedding model.
            top_k: Maximum number of results to return.
            threshold: Optional similarity threshold (0-1).
            query_text: Original query text for hybrid search boosting.
            use_hybrid: If True and query_text provided, use hybrid search.

        Returns:
            List of result dictionaries with chunk_id, content, file_path,
            page, score, source, filename.
        """
        pass

    @abstractmethod
    def delete_document(self, file_path: str) -> Dict:
        """Delete a document and all its chunks.

        Cascades to remove vectors and FTS entries.

        Args:
            file_path: Full path of document to delete.

        Returns:
            Dictionary with:
            - found: bool - whether document existed
            - document_id: int - ID of deleted document (if found)
            - chunks_deleted: int - number of chunks removed
            - document_deleted: bool - whether deletion succeeded
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict:
        """Get database statistics.

        Returns:
            Dictionary with:
            - indexed_documents: int - total document count
            - total_chunks: int - total chunk count
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the vector store and release resources.

        For SQLite/vectorlite, this persists the HNSW index.
        Should be called on application shutdown.
        """
        pass


class GraphRepository(ABC):
    """Abstract knowledge graph repository interface.

    Stores and queries the knowledge graph for Graph-RAG.
    Nodes represent notes, tags, concepts.
    Edges represent wikilinks, tag relationships.

    This is optional - not all applications use Graph-RAG.
    """

    @abstractmethod
    def add_node(self, node_id: str, node_type: str, title: str,
                 content: str = None, metadata: str = None) -> None:
        """Add or update a graph node.

        Args:
            node_id: Unique identifier (e.g., "note:filename" or "tag:name").
            node_type: Type of node ("note", "tag", "concept", "note_ref").
            title: Display title for the node.
            content: Optional text content.
            metadata: Optional JSON metadata string.
        """
        pass

    @abstractmethod
    def add_edge(self, source_id: str, target_id: str, edge_type: str,
                 metadata: str = None) -> None:
        """Add an edge between nodes.

        Args:
            source_id: Source node ID.
            target_id: Target node ID.
            edge_type: Type of edge ("wikilink", "tag", "header").
            metadata: Optional JSON metadata string.
        """
        pass

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a node by ID.

        Args:
            node_id: Node ID to retrieve.

        Returns:
            Node dictionary or None if not found.
        """
        pass

    @abstractmethod
    def get_edges_from(self, source_id: str) -> List[Dict]:
        """Get all edges from a source node.

        Args:
            source_id: Source node ID.

        Returns:
            List of edge dictionaries.
        """
        pass

    @abstractmethod
    def get_edges_to(self, target_id: str) -> List[Dict]:
        """Get all edges to a target node.

        Args:
            target_id: Target node ID.

        Returns:
            List of edge dictionaries.
        """
        pass

    @abstractmethod
    def delete_node(self, node_id: str) -> None:
        """Delete a node and its edges.

        Args:
            node_id: Node ID to delete.
        """
        pass

    @abstractmethod
    def get_graph_stats(self) -> Dict:
        """Get graph statistics.

        Returns:
            Dictionary with node/edge counts by type.
        """
        pass


class ProgressTracker(ABC):
    """Abstract progress tracking interface for resumable processing.

    Tracks document processing state to enable resume after interruption.
    """

    @abstractmethod
    def start_processing(self, file_path: str, file_hash: str, total_chunks: int) -> None:
        """Mark a file as starting processing.

        Args:
            file_path: Full path to file being processed.
            file_hash: SHA256 hash of file content.
            total_chunks: Expected number of chunks to process.
        """
        pass

    @abstractmethod
    def update_progress(self, file_path: str, chunks_processed: int,
                       last_chunk_end: int = None) -> None:
        """Update processing progress.

        Args:
            file_path: File being processed.
            chunks_processed: Number of chunks completed.
            last_chunk_end: Byte offset of last processed chunk (for resume).
        """
        pass

    @abstractmethod
    def mark_completed(self, file_path: str) -> None:
        """Mark file processing as completed.

        Args:
            file_path: File that completed processing.
        """
        pass

    @abstractmethod
    def mark_failed(self, file_path: str, error_message: str) -> None:
        """Mark file processing as failed.

        Args:
            file_path: File that failed.
            error_message: Error description for debugging.
        """
        pass

    @abstractmethod
    def get_status(self, file_path: str) -> Optional[Dict]:
        """Get processing status for a file.

        Args:
            file_path: File to check status for.

        Returns:
            Status dictionary or None if not tracked.
        """
        pass

    @abstractmethod
    def get_incomplete(self) -> List[Dict]:
        """Get all files with incomplete processing.

        Returns:
            List of status dictionaries for resumable files.
        """
        pass


class HybridSearcher(ABC):
    """Abstract hybrid search interface.

    Combines vector similarity search with keyword-based BM25 search
    using Reciprocal Rank Fusion (RRF) to produce better results than
    either method alone.

    Implementations:
    - SQLite: HybridSearcher in hybrid_search.py (uses rank_bm25 + SQLite)
    - PostgreSQL: PostgresHybridSearcher in hybrid_search.py (uses rank_bm25 + psycopg2)

    Usage:
        from ingestion.database_factory import DatabaseFactory

        # Get hybrid searcher for current backend
        searcher = DatabaseFactory.create_hybrid_searcher(conn)

        # Search with hybrid ranking
        results = searcher.search(query, vector_results, top_k=10)

        # Refresh after document changes
        searcher.refresh_keyword_index()
    """

    @abstractmethod
    def search(self, query: str, vector_results: List[Dict],
               top_k: int) -> List[Dict]:
        """Execute hybrid search combining vector and keyword results.

        Uses Reciprocal Rank Fusion to merge vector similarity results
        with BM25 keyword scores. The keyword search provides complementary
        signal that helps when:
        - Exact keyword matches are important (book titles, code identifiers)
        - Vector similarity alone returns semantically similar but wrong results
        - Users search with technical terms that should match exactly

        Args:
            query: The user's search query text.
            vector_results: Results from vector similarity search, as list of dicts
                           with keys: chunk_id, content, file_path, page, score.
            top_k: Number of results to return after fusion.

        Returns:
            List of result dictionaries sorted by fused score, containing:
            - chunk_id: Database ID of the chunk
            - content: Text content of the chunk
            - file_path: Path to source document
            - page: Page number if applicable
            - score: Fused relevance score
        """
        pass

    @abstractmethod
    def refresh_keyword_index(self) -> None:
        """Rebuild the keyword (BM25) index from current database contents.

        Must be called after adding, updating, or deleting documents
        to ensure keyword search reflects current data. This is separate
        from vector index maintenance.

        Note: For large databases, this can be expensive. Consider batching
        updates and refreshing periodically rather than after each change.
        """
        pass
