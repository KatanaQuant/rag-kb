# Copyright (c) 2024 RAG-KB Contributors
# SPDX-License-Identifier: MIT

"""Security scan result caching service

Caches ClamAV/YARA/hash blacklist scan results by file hash to avoid
re-scanning unchanged files. This dramatically speeds up:
- Retroactive security scans
- File validation during indexing (when same file is processed twice)
- Startup validation of existing files

Cache invalidation:
- File content changes → new hash → cache miss → re-scan
- Manual cache clear via API
- TTL-based expiry (optional, default: no expiry)
"""
import sqlite3
import json
from pathlib import Path
from typing import Optional
from datetime import datetime
from dataclasses import dataclass

from config import default_config


# Scanner version - bump this to invalidate all cached results
# when scanner rules/signatures are updated
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


class SecurityScanCache:
    """Cache for security scan results

    Uses SQLite table to persist scan results by file hash.
    Thread-safe for concurrent access.
    """

    def __init__(self, db_path: str = None):
        """Initialize cache

        Args:
            db_path: Path to SQLite database. Defaults to config.
        """
        self.db_path = db_path or default_config.database.path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, file_hash: str) -> Optional[CachedScanResult]:
        """Get cached scan result for file hash

        Args:
            file_hash: SHA256 hash of file content

        Returns:
            CachedScanResult if found and valid, None otherwise
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM security_scan_cache
                WHERE file_hash = ? AND scanner_version = ?
                """,
                (file_hash, SCANNER_VERSION)
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Parse matches JSON
            matches = []
            if row['matches_json']:
                try:
                    matches = json.loads(row['matches_json'])
                except json.JSONDecodeError:
                    pass

            return CachedScanResult(
                file_hash=row['file_hash'],
                is_valid=bool(row['is_valid']),
                severity=row['severity'],
                reason=row['reason'] or '',
                validation_check=row['validation_check'] or '',
                matches=matches,
                scanned_at=row['scanned_at'],
                scanner_version=row['scanner_version']
            )
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return None
        finally:
            conn.close()

    def set(
        self,
        file_hash: str,
        is_valid: bool,
        severity: Optional[str] = None,
        reason: str = '',
        validation_check: str = '',
        matches: list = None
    ) -> None:
        """Cache a scan result

        Args:
            file_hash: SHA256 hash of file content
            is_valid: Whether file passed validation
            severity: Security severity level (CRITICAL, WARNING, INFO)
            reason: Reason for validation result
            validation_check: Name of validation strategy
            matches: List of security matches (YARA rules, etc)
        """
        conn = self._get_connection()
        try:
            matches_json = json.dumps(matches or [])

            conn.execute(
                """
                INSERT OR REPLACE INTO security_scan_cache
                (file_hash, is_valid, severity, reason, validation_check,
                 matches_json, scanned_at, scanner_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
                    is_valid,
                    severity,
                    reason,
                    validation_check,
                    matches_json,
                    datetime.now().isoformat(),
                    SCANNER_VERSION
                )
            )
            conn.commit()
        except sqlite3.OperationalError:
            # Table doesn't exist - will be created on next startup
            pass
        finally:
            conn.close()

    def clear(self) -> int:
        """Clear all cached scan results

        Returns:
            Number of entries cleared
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM security_scan_cache")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM security_scan_cache")
            conn.commit()
            return count
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    def clear_old(self, days: int = 30) -> int:
        """Clear cached results older than specified days

        Args:
            days: Clear entries older than this many days

        Returns:
            Number of entries cleared
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                DELETE FROM security_scan_cache
                WHERE scanned_at < datetime('now', ?)
                """,
                (f'-{days} days',)
            )
            conn.commit()
            return cursor.rowcount
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    def stats(self) -> dict:
        """Get cache statistics

        Returns:
            Dict with total_entries, valid_count, invalid_count, oldest_entry
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid_count,
                    SUM(CASE WHEN NOT is_valid THEN 1 ELSE 0 END) as invalid_count,
                    MIN(scanned_at) as oldest,
                    MAX(scanned_at) as newest
                FROM security_scan_cache
                WHERE scanner_version = ?
            """, (SCANNER_VERSION,))
            row = cursor.fetchone()

            return {
                'total_entries': row['total'] or 0,
                'valid_count': row['valid_count'] or 0,
                'invalid_count': row['invalid_count'] or 0,
                'oldest_entry': row['oldest'],
                'newest_entry': row['newest'],
                'scanner_version': SCANNER_VERSION
            }
        except sqlite3.OperationalError:
            return {
                'total_entries': 0,
                'valid_count': 0,
                'invalid_count': 0,
                'oldest_entry': None,
                'newest_entry': None,
                'scanner_version': SCANNER_VERSION
            }
        finally:
            conn.close()


# Global cache instance
_cache: Optional[SecurityScanCache] = None


def get_security_cache() -> SecurityScanCache:
    """Get global security scan cache instance"""
    global _cache
    if _cache is None:
        _cache = SecurityScanCache()
    return _cache
