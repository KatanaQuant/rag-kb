"""Security scan result caching service for PostgreSQL

Caches ClamAV/YARA/hash blacklist scan results by file hash to avoid
re-scanning unchanged files.
"""
import json
from typing import Optional
from datetime import datetime
from dataclasses import dataclass

from config import default_config
from ingestion.database_factory import DatabaseFactory


# Scanner version - bump this to invalidate all cached results
SCANNER_VERSION = "1.0.0"


@dataclass
class CachedScanResult:
    """Cached security scan result"""
    file_hash: str
    is_valid: bool
    severity: Optional[str]
    reason: str
    validation_check: str
    matches: list
    scanned_at: str
    scanner_version: str


class PostgresSecurityScanCache:
    """Cache for security scan results using PostgreSQL."""

    def __init__(self, config=default_config.database):
        self.config = config
        self.db_conn = None

    def _get_connection(self):
        """Get database connection"""
        if self.db_conn is None:
            self.db_conn = DatabaseFactory.create_connection(self.config)
        return self.db_conn.connect()

    def _close_connection(self):
        """Close database connection"""
        if self.db_conn:
            self.db_conn.close()
            self.db_conn = None

    def get(self, file_hash: str) -> Optional[CachedScanResult]:
        """Get cached scan result for file hash"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT file_hash, is_valid, severity, reason, validation_check,
                           matches_json, scanned_at, scanner_version
                    FROM security_scan_cache
                    WHERE file_hash = %s AND scanner_version = %s
                """, (file_hash, SCANNER_VERSION))
                row = cur.fetchone()
                return self._row_to_result(row) if row else None
        except Exception:
            return None

    def _row_to_result(self, row) -> CachedScanResult:
        """Convert database row to CachedScanResult"""
        matches = json.loads(row[5]) if row[5] else []
        scanned_at = row[6].isoformat() if hasattr(row[6], 'isoformat') else str(row[6])
        return CachedScanResult(
            file_hash=row[0],
            is_valid=row[1],
            severity=row[2],
            reason=row[3],
            validation_check=row[4],
            matches=matches,
            scanned_at=scanned_at,
            scanner_version=row[7]
        )

    def set(self, file_hash: str, is_valid: bool, severity: Optional[str],
            reason: str, validation_check: str, matches: list = None):
        """Cache scan result for file hash"""
        conn = self._get_connection()
        now = datetime.utcnow().isoformat()
        matches_json = json.dumps(matches or [])

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO security_scan_cache
                (file_hash, is_valid, severity, reason, validation_check,
                 matches_json, scanned_at, scanner_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (file_hash) DO UPDATE SET
                    is_valid = EXCLUDED.is_valid,
                    severity = EXCLUDED.severity,
                    reason = EXCLUDED.reason,
                    validation_check = EXCLUDED.validation_check,
                    matches_json = EXCLUDED.matches_json,
                    scanned_at = EXCLUDED.scanned_at,
                    scanner_version = EXCLUDED.scanner_version
            """, (file_hash, is_valid, severity, reason, validation_check,
                  matches_json, now, SCANNER_VERSION))
        conn.commit()

    def clear(self):
        """Clear all cached results"""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM security_scan_cache")
        conn.commit()

    def clear_outdated(self):
        """Clear results from old scanner versions"""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM security_scan_cache WHERE scanner_version != %s",
                (SCANNER_VERSION,)
            )
            count = cur.rowcount
        conn.commit()
        return count

    def get_stats(self) -> dict:
        """Get cache statistics"""
        conn = self._get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM security_scan_cache")
            total = cur.fetchone()[0]

            cur.execute("""
                SELECT is_valid, COUNT(*)
                FROM security_scan_cache
                GROUP BY is_valid
            """)
            by_validity = dict(cur.fetchall())

            cur.execute("""
                SELECT scanner_version, COUNT(*)
                FROM security_scan_cache
                GROUP BY scanner_version
            """)
            by_version = dict(cur.fetchall())

        return {
            'total_entries': total,
            'valid_files': by_validity.get(True, 0),
            'invalid_files': by_validity.get(False, 0),
            'current_version': SCANNER_VERSION,
            'by_version': by_version
        }


# Alias for compatibility
SecurityScanCache = PostgresSecurityScanCache

# Singleton instance
_cache = None


def get_security_cache() -> PostgresSecurityScanCache:
    """Get global security scan cache instance"""
    global _cache
    if _cache is None:
        _cache = PostgresSecurityScanCache()
    return _cache
