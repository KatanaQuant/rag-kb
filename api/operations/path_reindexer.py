"""Path-based reindexing service

Handles deleting and re-queuing specific files or directories for reindexing.
"""
from pathlib import Path
from typing import List, Optional, Set
from dataclasses import dataclass, field

from pipeline.indexing_queue import Priority


@dataclass
class PathReindexResult:
    """Result for a single file reindex operation"""
    file_path: str
    filename: str
    deleted_from_db: bool
    queued: bool
    chunks_deleted: int = 0
    error: Optional[str] = None


@dataclass
class PathReindexSummary:
    """Summary of path reindex operation"""
    path: str
    is_directory: bool
    files_found: int
    files_deleted: int
    files_queued: int
    total_chunks_deleted: int
    dry_run: bool
    results: List[PathReindexResult] = field(default_factory=list)
    message: str = ""


class PathReindexer:
    """Service to delete and re-queue files at a specific path for reindexing

    Supports both single files and directories (recursive).
    """

    MAX_RESULTS = 100

    def __init__(self, vector_store, progress_tracker, indexing_queue,
                 supported_extensions: Optional[Set[str]] = None):
        """Initialize the path reindexer

        Args:
            vector_store: Sync VectorStore for deletion operations
            progress_tracker: ProcessingProgressTracker for progress deletion
            indexing_queue: IndexingQueue for queueing files
            supported_extensions: Set of supported file extensions (e.g., {'.pdf', '.md'})
        """
        self.vector_store = vector_store
        self.progress_tracker = progress_tracker
        self.indexing_queue = indexing_queue
        self.supported_extensions = supported_extensions or self._default_extensions()

    @staticmethod
    def _default_extensions() -> Set[str]:
        """Default supported extensions"""
        return {
            '.pdf', '.md', '.markdown', '.docx', '.epub',
            '.py', '.java', '.ts', '.tsx', '.js', '.jsx', '.cs', '.go',
            '.ipynb'
        }

    def reindex(self, path: str, dry_run: bool = False) -> PathReindexSummary:
        """Delete and re-queue files at the given path

        Args:
            path: File or directory path to reindex
            dry_run: If True, report what would be done without making changes

        Returns:
            PathReindexSummary with operation results
        """
        target = Path(path)

        if not target.exists():
            return self._not_found_summary(path, dry_run)

        if target.is_file():
            return self._reindex_file(target, dry_run)
        elif target.is_dir():
            return self._reindex_directory(target, dry_run)
        else:
            return self._invalid_path_summary(path, dry_run)

    def _reindex_file(self, file_path: Path, dry_run: bool) -> PathReindexSummary:
        """Reindex a single file"""
        if not self._is_supported(file_path):
            return PathReindexSummary(
                path=str(file_path),
                is_directory=False,
                files_found=1,
                files_deleted=0,
                files_queued=0,
                total_chunks_deleted=0,
                dry_run=dry_run,
                results=[PathReindexResult(
                    file_path=str(file_path),
                    filename=file_path.name,
                    deleted_from_db=False,
                    queued=False,
                    error=f"Unsupported file type: {file_path.suffix}"
                )],
                message=f"File type {file_path.suffix} is not supported"
            )

        result = self._process_file(file_path, dry_run)

        files_deleted = 1 if result.deleted_from_db else 0
        files_queued = 1 if result.queued else 0

        action = "Would reindex" if dry_run else "Reindexed"
        return PathReindexSummary(
            path=str(file_path),
            is_directory=False,
            files_found=1,
            files_deleted=files_deleted,
            files_queued=files_queued,
            total_chunks_deleted=result.chunks_deleted,
            dry_run=dry_run,
            results=[result],
            message=f"{action} {file_path.name}"
        )

    def _reindex_directory(self, dir_path: Path, dry_run: bool) -> PathReindexSummary:
        """Reindex all supported files in a directory recursively"""
        files = list(self._find_supported_files(dir_path))

        if not files:
            return PathReindexSummary(
                path=str(dir_path),
                is_directory=True,
                files_found=0,
                files_deleted=0,
                files_queued=0,
                total_chunks_deleted=0,
                dry_run=dry_run,
                results=[],
                message=f"No supported files found in {dir_path}"
            )

        results = []
        total_chunks = 0
        files_deleted = 0
        files_queued = 0

        for file_path in files:
            result = self._process_file(file_path, dry_run)
            results.append(result)
            total_chunks += result.chunks_deleted
            if result.deleted_from_db:
                files_deleted += 1
            if result.queued:
                files_queued += 1

        action = "Would reindex" if dry_run else "Reindexed"
        return PathReindexSummary(
            path=str(dir_path),
            is_directory=True,
            files_found=len(files),
            files_deleted=files_deleted,
            files_queued=files_queued,
            total_chunks_deleted=total_chunks,
            dry_run=dry_run,
            results=results[:self.MAX_RESULTS],
            message=f"{action} {len(files)} files from {dir_path.name}/"
        )

    def _find_supported_files(self, dir_path: Path):
        """Yield all supported files in directory recursively"""
        for file_path in dir_path.rglob("*"):
            if file_path.is_file() and self._is_supported(file_path):
                yield file_path

    def _is_supported(self, path: Path) -> bool:
        """Check if file extension is supported"""
        return path.suffix.lower() in self.supported_extensions

    def _process_file(self, file_path: Path, dry_run: bool) -> PathReindexResult:
        """Process a single file: delete from DB and queue for reindexing"""
        file_path_str = str(file_path)
        chunks_deleted = 0
        deleted_from_db = False
        queued = False
        error = None

        if dry_run:
            # In dry run, just check if file exists in DB
            try:
                deleted_from_db = self._file_exists_in_db(file_path_str)
                queued = True  # Would be queued
            except Exception as e:
                error = str(e)
        else:
            # Actually delete and queue
            try:
                delete_result = self._delete_from_db(file_path_str)
                chunks_deleted = delete_result.get('chunks_deleted', 0)
                deleted_from_db = delete_result.get('found', False)
            except Exception as e:
                error = f"Delete failed: {e}"

            try:
                self._queue_for_reindex(file_path)
                queued = True
            except Exception as e:
                if error:
                    error += f"; Queue failed: {e}"
                else:
                    error = f"Queue failed: {e}"

        return PathReindexResult(
            file_path=file_path_str,
            filename=file_path.name,
            deleted_from_db=deleted_from_db,
            queued=queued,
            chunks_deleted=chunks_deleted,
            error=error
        )

    def _file_exists_in_db(self, file_path: str) -> bool:
        """Check if file exists in database (for dry run)"""
        if not self.vector_store:
            return False
        try:
            # Use get_document_info or similar to check existence
            info = self.vector_store.get_document_info_by_path(file_path)
            return info is not None
        except AttributeError:
            # Fallback: try to get stats
            return False
        except Exception:
            return False

    def _delete_from_db(self, file_path: str) -> dict:
        """Delete file from database"""
        result = {'found': False, 'chunks_deleted': 0}

        if self.vector_store:
            try:
                result = self.vector_store.delete_document(file_path)
            except Exception:
                pass  # Document may not exist

        if self.progress_tracker:
            try:
                self.progress_tracker.delete_document(file_path)
            except Exception:
                pass  # Progress record may not exist

        return result

    def _queue_for_reindex(self, file_path: Path) -> None:
        """Queue file for reindexing with HIGH priority"""
        if self.indexing_queue:
            self.indexing_queue.add(file_path, priority=Priority.HIGH, force=True)

    def _not_found_summary(self, path: str, dry_run: bool) -> PathReindexSummary:
        """Return summary for non-existent path"""
        return PathReindexSummary(
            path=path,
            is_directory=False,
            files_found=0,
            files_deleted=0,
            files_queued=0,
            total_chunks_deleted=0,
            dry_run=dry_run,
            results=[],
            message=f"Path not found: {path}"
        )

    def _invalid_path_summary(self, path: str, dry_run: bool) -> PathReindexSummary:
        """Return summary for invalid path (not file or directory)"""
        return PathReindexSummary(
            path=path,
            is_directory=False,
            files_found=0,
            files_deleted=0,
            files_queued=0,
            total_chunks_deleted=0,
            dry_run=dry_run,
            results=[],
            message=f"Invalid path (not a file or directory): {path}"
        )
