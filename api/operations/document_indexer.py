from pathlib import Path
from typing import List
from domain_models import DocumentFile
from ingestion import FileHasher
from value_objects import ProcessingResult, DocumentIdentity


class DocumentIndexer:
    """Handles document indexing operations with async embedding"""

    def __init__(self, processor, embedding_service):
        self.processor = processor
        self.embedding_service = embedding_service

    def index_file(self, file_path: Path, force: bool = False, stage_callback=None) -> ProcessingResult:
        """Index single file. Returns ProcessingResult"""
        self.stage_callback = stage_callback
        if not self._should_index(file_path, force):
            return ProcessingResult.skipped()
        chunks = self._do_index(file_path)
        return ProcessingResult.success(chunks_count=chunks)

    def _should_index(self, path: Path, force: bool) -> bool:
        """Check if should index"""
        if force:
            return True
        return self._needs_indexing(path)

    def _needs_indexing(self, path: Path) -> bool:
        """Check if file needs indexing"""
        file_hash = FileHasher.hash_file(path)
        indexed = self.embedding_service.is_indexed(str(path), file_hash)
        return not indexed

    def _do_index(self, path: Path) -> int:
        """Perform indexing

        Using encapsulation principle: Let DocumentFile create itself
        """
        print(f"[DEBUG] _do_index: stage_callback is {'SET' if self.stage_callback else 'NONE'}")
        if self.stage_callback:
            self.stage_callback("extracting")
        doc_file = DocumentFile.from_path(path)
        chunks = self._get_chunks(doc_file)
        return self._store_if_valid(doc_file, chunks)

    def _get_chunks(self, doc_file: DocumentFile) -> List:
        """Extract chunks from file"""
        if self.stage_callback:
            self.stage_callback("chunking")
        chunks = self.processor.process_file(doc_file)
        return chunks

    def _store_if_valid(self, doc_file: DocumentFile, chunks: List) -> int:
        """Store chunks if valid"""
        if not chunks:
            self.embedding_service.add_empty_document(
                file_path=str(doc_file.path),
                file_hash=doc_file.hash
            )
            self.processor.delete_from_tracker(str(doc_file.path))
            return 0
        if self.stage_callback:
            self.stage_callback("embedding")
        self._store_chunks(doc_file, chunks)
        if self.stage_callback:
            self.stage_callback("storing")
        return len(chunks)

    def _store_chunks(self, doc_file: DocumentFile, chunks: List):
        """Store chunks with async embeddings"""
        identity = DocumentIdentity.from_file(doc_file.path, doc_file.hash)
        self.embedding_service.queue_embedding(identity, chunks)

    def wait_for_pending(self):
        """Wait for all pending embeddings to complete"""
        self.embedding_service.wait_for_all()

    def get_obsidian_graph(self):
        """Get Obsidian knowledge graph.

        Delegation method to avoid Law of Demeter violation.
        """
        return self.processor.get_obsidian_graph()
