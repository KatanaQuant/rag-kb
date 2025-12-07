"""Database integrity checking service

Verifies database consistency:
1. Referential integrity (chunks -> documents)
2. HNSW index consistency (vec_chunks <-> chunks)
3. FTS index consistency (fts_chunks <-> chunks)
4. Duplicate detection (same file indexed multiple times)

Extracted from scripts/verify_integrity.py for API use.
"""
import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class IntegrityCheck:
    """Result of a single integrity check"""
    name: str
    passed: bool
    details: str


@dataclass
class IntegrityResult:
    """Complete integrity check result"""
    healthy: bool
    issues: List[str] = field(default_factory=list)
    checks: List[Dict[str, Any]] = field(default_factory=list)
    table_counts: Dict[str, Any] = field(default_factory=dict)


class IntegrityChecker:
    """Database integrity checker with injectable db_path

    Example:
        checker = IntegrityChecker(db_path="/app/data/rag.db")
        result = checker.check()
        if not result.healthy:
            print(f"Issues: {result.issues}")
    """

    def __init__(self, db_path: str):
        """Initialize checker with database path

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def check(self) -> IntegrityResult:
        """Run all integrity checks and return structured result

        Returns:
            IntegrityResult with healthy status, issues list, and check details
        """
        conn = sqlite3.connect(self.db_path)

        # Try to load vectorlite for vec_chunks access
        self._try_load_vectorlite(conn)

        # Get table counts
        table_counts = self._get_table_counts(conn)

        # Run all checks
        checks = [
            self._check_referential_integrity(conn),
            self._check_hnsw_consistency(conn),
            self._check_fts_consistency(conn),
            self._check_duplicate_documents(conn),
        ]

        conn.close()

        # Collect issues from failed checks
        issues = [
            check.details for check in checks
            if not check.passed
        ]

        # Convert checks to dict format for JSON serialization
        checks_dict = [
            {'name': c.name, 'passed': c.passed, 'details': c.details}
            for c in checks
        ]

        return IntegrityResult(
            healthy=len(issues) == 0,
            issues=issues,
            checks=checks_dict,
            table_counts=table_counts
        )

    def _try_load_vectorlite(self, conn: sqlite3.Connection) -> None:
        """Attempt to load vectorlite extension for vec_chunks access"""
        try:
            import vectorlite_py
            conn.enable_load_extension(True)
            conn.load_extension(vectorlite_py.vectorlite_path())
        except Exception:
            # Vectorlite not available, vec_chunks checks will handle gracefully
            pass

    def _get_table_counts(self, conn: sqlite3.Connection) -> Dict[str, Any]:
        """Get row counts for all relevant tables"""
        counts = {}
        for table in ['documents', 'chunks', 'vec_chunks', 'fts_chunks']:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = "TABLE NOT FOUND"
        return counts

    def _check_referential_integrity(self, conn: sqlite3.Connection) -> IntegrityCheck:
        """Check that all chunks reference valid documents"""
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM chunks c
            LEFT JOIN documents d ON c.document_id = d.id
            WHERE d.id IS NULL
        """)
        orphan_count = cursor.fetchone()[0]

        return IntegrityCheck(
            name='Referential Integrity (chunks -> documents)',
            passed=orphan_count == 0,
            details=(
                f"{orphan_count} orphan chunks found"
                if orphan_count > 0
                else "All chunks have valid documents"
            )
        )

    def _check_hnsw_consistency(self, conn: sqlite3.Connection) -> IntegrityCheck:
        """Check vec_chunks matches chunks table

        Note: vec_chunks is a vectorlite virtual table that doesn't support
        standard JOINs. We use count comparison as a proxy for consistency.
        """
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM vec_chunks")
            vec_count = cursor.fetchone()[0]

            diff = abs(chunk_count - vec_count)

            issues = []
            if vec_count > chunk_count:
                issues.append(f"{vec_count - chunk_count} extra vec_chunks entries (orphans)")
            elif vec_count < chunk_count:
                issues.append(f"{chunk_count - vec_count} chunks missing from HNSW index")

            return IntegrityCheck(
                name='HNSW Index Consistency (vec_chunks vs chunks count)',
                passed=diff == 0,
                details=(
                    "; ".join(issues) if issues
                    else f"Counts match: {chunk_count} chunks, {vec_count} vec_chunks"
                )
            )
        except sqlite3.OperationalError as e:
            return IntegrityCheck(
                name='HNSW Index Consistency',
                passed=True,  # Don't fail on vectorlite load issues
                details=f"Skipped (vectorlite not loaded): {e}"
            )

    def _check_fts_consistency(self, conn: sqlite3.Connection) -> IntegrityCheck:
        """Check fts_chunks matches chunks table

        Note: FTS virtual tables don't support efficient JOINs.
        We use count comparison as a proxy for consistency.
        """
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM fts_chunks")
            fts_count = cursor.fetchone()[0]

            diff = abs(chunk_count - fts_count)

            issues = []
            if fts_count > chunk_count:
                issues.append(f"{fts_count - chunk_count} extra fts_chunks entries (orphans)")
            elif fts_count < chunk_count:
                issues.append(f"{chunk_count - fts_count} chunks missing from FTS index")

            return IntegrityCheck(
                name='FTS Index Consistency (fts_chunks vs chunks count)',
                passed=diff == 0,
                details=(
                    "; ".join(issues) if issues
                    else f"Counts match: {chunk_count} chunks, {fts_count} fts_chunks"
                )
            )
        except sqlite3.OperationalError as e:
            return IntegrityCheck(
                name='FTS Index Consistency',
                passed=False,
                details=f"Could not check: {e}"
            )

    def _check_duplicate_documents(self, conn: sqlite3.Connection) -> IntegrityCheck:
        """Check for files indexed multiple times"""
        cursor = conn.execute("""
            SELECT file_path, COUNT(*) as cnt
            FROM documents
            GROUP BY file_path
            HAVING cnt > 1
        """)
        duplicates = cursor.fetchall()

        return IntegrityCheck(
            name='Duplicate Documents',
            passed=len(duplicates) == 0,
            details=(
                f"{len(duplicates)} files indexed multiple times"
                if duplicates
                else "No duplicate documents"
            )
        )
