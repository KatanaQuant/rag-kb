"""
Async database connection management.

Extracted from async_database.py following Sandi Metz POODR principles:
- Single Responsibility: Connection lifecycle only
- One class per file for clarity
"""

import aiosqlite
from config import default_config


class AsyncDatabaseConnection:
    """Manages async SQLite connection and extensions.

    Single responsibility: Database connection lifecycle
    """

    def __init__(self, config=default_config.database):
        self.config = config
        self.conn = None

    async def connect(self) -> aiosqlite.Connection:
        """Establish async database connection"""
        self.conn = await self._create_connection()
        # Enable WAL mode for better concurrency (allows concurrent reads during writes)
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s for locks
        await self._load_extension()
        return self.conn

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create async SQLite connection"""
        return await aiosqlite.connect(
            self.config.path,
            check_same_thread=False  # aiosqlite handles threading
        )

    async def _load_extension(self):
        """Load vector extension"""
        if not self.config.require_vec_extension:
            return
        await self._load_python_bindings()

    async def _load_python_bindings(self):
        """Load sqlite-vec using Python bindings

        Note: aiosqlite doesn't support enable_load_extension() directly,
        so we use the Python bindings which are already in use.
        """
        try:
            import sqlite_vec
            # Access underlying sqlite3.Connection to load extension
            # aiosqlite wraps sqlite3.Connection as ._conn
            sqlite_vec.load(self.conn._conn)
        except Exception as e:
            raise RuntimeError(f"sqlite-vec failed: {e}")

    async def close(self):
        """Close connection"""
        if self.conn:
            await self.conn.close()
