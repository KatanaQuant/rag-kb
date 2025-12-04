"""Sanitization stage for database consistency"""

import os

class Sanitizer:
    """Sanitizes database before indexing

    Design principles:
    - Single responsibility: database sanitization
    - Small methods (< 5 lines each)
    - Clear method names
    """

    def __init__(self, state, factory):
        self.state = state
        self.factory = factory

    def sanitize(self):
        """Run sanitization stage"""
        if not self.state.progress_tracker:
            return
        print("\n=== Starting Sanitization Stage ===")
        self._resume_incomplete()
        self._repair_orphans()
        print("=== Sanitization Complete ===\n")

    def _resume_incomplete(self):
        """Resume incomplete files"""
        print("Checking for incomplete files...")
        orchestrator = self.factory.create_orchestrator()
        orchestrator.resume_incomplete_processing()

    def _repair_orphans(self):
        """Repair orphaned files if enabled"""
        if not self._is_auto_repair_enabled():
            print("Auto-repair disabled, skipping orphan check")
            return
        self._check_and_repair()

    def _is_auto_repair_enabled(self) -> bool:
        """Check if auto-repair is enabled"""
        return os.getenv('AUTO_REPAIR_ORPHANS', 'true').lower() == 'true'

    def _check_and_repair(self):
        """Check for orphans and repair"""
        detector = self._create_detector()
        orphans = detector.detect_orphans()
        if not orphans:
            print("No orphaned files found")
            return
        self._repair(detector, orphans)

    def _create_detector(self):
        """Create orphan detector"""
        from main import OrphanDetector
        return OrphanDetector(
            self.state.progress_tracker,
            self.state.vector_store
        )

    def _repair(self, detector, orphans):
        """Repair orphaned files"""
        print(f"Found {len(orphans)} orphaned files")
        print("Repairing orphans before starting new indexing...\n")
        indexer = self.factory.create_indexer()
        detector.repair_orphans(indexer)
        print("Orphan repair complete")
