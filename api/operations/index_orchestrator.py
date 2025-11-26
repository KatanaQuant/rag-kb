from pathlib import Path
from typing import List
from collections import defaultdict
from operations.file_walker import FileWalker


class IndexOrchestrator:
    """Orchestrates full indexing process via queue

    All file processing routes through IndexingQueue for concurrent pipeline processing.
    """

    def __init__(self, base_path: Path, indexer, processor, progress_tracker=None, queue=None):
        self.base_path = base_path
        self.indexer = indexer
        self.walker = self._create_walker(base_path, processor)
        self.tracker = progress_tracker
        self.queue = queue

    @staticmethod
    def _create_walker(base_path, processor):
        """Create file walker"""
        return FileWalker(base_path, processor.SUPPORTED_EXTENSIONS)

    def resume_incomplete_processing(self):
        """Resume processing incomplete files"""
        if not self.tracker:
            return
        incomplete = self.tracker.get_incomplete_files()
        if not incomplete:
            return
        print(f"Resuming {len(incomplete)} incomplete files...")
        self._process_incomplete(incomplete)

    def _process_incomplete(self, incomplete):
        """Process incomplete files"""
        for progress in incomplete:
            self._resume_one(progress)

    def _resume_one(self, progress):
        """Add incomplete file to queue with HIGH priority for reprocessing"""
        try:
            file_path = Path(progress.file_path)
            if not file_path.exists():
                self.tracker.mark_failed(progress.file_path, "File no longer exists")
                return

            if not self.queue:
                print(f"WARNING: No queue available, cannot resume {file_path.name}")
                return

            from pipeline import Priority
            self.queue.add(file_path, priority=Priority.HIGH, force=True)
            print(f"Queued incomplete file for reprocessing: {file_path.name}")
        except Exception as e:
            print(f"Failed to queue {progress.file_path}: {e}")
            self.tracker.mark_failed(progress.file_path, str(e))

    def index_all(self, queue, force: bool = False) -> tuple[int, int]:
        """Index all documents via queue

        All files are added to the queue for concurrent pipeline processing.

        Args:
            queue: IndexingQueue for file processing (required)
            force: If True, reindex even if already indexed

        Returns:
            Tuple of (files_queued, 0) - chunks count is 0 as processing is async
        """
        if not self.base_path.exists():
            return self._handle_missing()
        return self._index_files(queue)

    def _handle_missing(self) -> tuple[int, int]:
        """Handle missing path"""
        print(f"Path missing: {self.base_path}")
        return 0, 0

    def _group_files_for_display(self, files: List[Path]) -> str:
        """Group files by directory for cleaner display"""
        root_pdfs, dir_groups = self._categorize_files(files)
        return self._build_display(root_pdfs, dir_groups)

    def _categorize_files(self, files: List[Path]) -> tuple:
        """Categorize files into root PDFs and directory groups"""
        root_pdfs = []
        dir_groups = defaultdict(list)
        for file_path in files:
            self._categorize_one(file_path, root_pdfs, dir_groups)
        return root_pdfs, dir_groups

    def _categorize_one(self, file_path: Path, root_pdfs: List, dir_groups: dict):
        """Categorize a single file"""
        parts = file_path.parts
        kb_index = parts.index('knowledge_base') if 'knowledge_base' in parts else -1
        if kb_index >= 0 and kb_index + 2 < len(parts):
            subdir = parts[kb_index + 1]
            dir_groups[subdir].append(file_path)
        elif file_path.suffix == '.pdf':
            root_pdfs.append(file_path)

    def _build_display(self, root_pdfs: List, dir_groups: dict) -> str:
        """Build display string from categorized files"""
        lines = []
        if root_pdfs:
            lines.extend(self._format_root_pdfs(root_pdfs))
        if dir_groups:
            if root_pdfs:
                lines.append("")
            lines.extend(self._format_directories(dir_groups))
        return "\n".join(lines)

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

    def _index_files(self, queue) -> tuple[int, int]:
        """Add all files to queue for concurrent pipeline processing

        Args:
            queue: IndexingQueue for file processing

        Returns:
            Tuple of (files_queued, 0) - chunks count is 0 as processing is async
        """
        all_files = list(self.walker.walk())
        if not all_files:
            return 0, 0
        self._print_files_found(all_files)
        return self._enqueue_files(all_files, queue)

    def _enqueue_files(self, all_files: List, queue) -> tuple[int, int]:
        """Add files to queue for worker processing"""
        from pipeline import Priority
        queue.add_many(all_files, priority=Priority.NORMAL)
        print(f"Added {len(all_files)} files to indexing queue")
        return len(all_files), 0

    def _print_files_found(self, all_files: List):
        """Print files found message"""
        print(f"Found {len(all_files)} files to process")
        print(self._group_files_for_display(all_files))

    def _persist_obsidian_graph(self):
        """Persist Obsidian knowledge graph to database"""
        try:
            graph_export = self._get_graph_export()
            if self._has_graph_content(graph_export):
                self._save_graph(graph_export)
        except Exception as e:
            print(f"Warning: Failed to persist graph: {e}")

    def _get_graph_export(self):
        """Get graph export from processor"""
        obsidian_graph = self.indexer.get_obsidian_graph()
        return obsidian_graph.export_graph()

    def _has_graph_content(self, graph_export):
        """Check if graph has content worth persisting"""
        return graph_export['stats']['total_nodes'] > 0

    def _save_graph(self, graph_export):
        """Save graph to database"""
        from ingestion.graph_repository import GraphRepository
        from ingestion.database import DatabaseConnection

        db = DatabaseConnection()
        conn = db.connect()
        graph_repo = GraphRepository(conn)
        graph_repo.persist_graph(graph_export)
        graph_repo.commit()
        db.close()
        self._print_graph_stats(graph_export)

    def _print_graph_stats(self, graph_export):
        """Print graph persistence statistics"""
        print(f"Graph persisted: {graph_export['stats']['total_nodes']} nodes, "
              f"{graph_export['stats']['total_edges']} edges")

