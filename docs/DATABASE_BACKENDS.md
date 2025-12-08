# Database Backend Architecture

This document describes the database abstraction layer that enables switching between different database backends.

## Overview

The RAG Knowledge Base supports multiple database backends through a clean abstraction layer:

| Backend | Status | Use Case |
|---------|--------|----------|
| **PostgreSQL + pgvector** | Default, Production | Full ACID, ARM64 support, recommended |
| **SQLite + vectorlite** | Legacy, Development | Single-file, no server needed |

## Architecture

```
┌─────────────────────────────────────────┐
│          APPLICATION LAYER              │
│  (routes, operations, startup)          │
│                                         │
│  Uses: DatabaseFactory, VectorStore     │
│  (interfaces only - no implementation)  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         ABSTRACTION LAYER               │
│  interfaces.py - ABC definitions        │
│  database_factory.py - runtime selection│
└─────────────────┬───────────────────────┘
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
┌─────────────┐       ┌─────────────┐
│ PostgreSQL  │       │   SQLite    │
│ + pgvector  │       │ + vectorlite│
│             │       │             │
│ postgres_*  │       │ database.py │
└─────────────┘       └─────────────┘
```

## Quick Start

### Switching Backends

Set the `DATABASE_URL` environment variable:

```bash
# PostgreSQL (default, recommended)
DATABASE_URL=postgresql://ragkb:ragkb@localhost:5432/ragkb

# SQLite (for development/testing)
DATABASE_URL=sqlite:///app/data/rag.db
```

No code changes required - the factory handles backend selection automatically.

### Using the Factory

```python
from ingestion import DatabaseFactory, VectorStoreInterface

# Auto-detect backend from DATABASE_URL
store = DatabaseFactory.create_vector_store()

# Explicit backend selection
store = DatabaseFactory.create_vector_store(config, backend='postgresql')

# Check which backend is configured
backend = DatabaseFactory.detect_backend(config)  # Returns 'postgresql' or 'sqlite'
```

### Convenience Functions

```python
from ingestion import get_vector_store, get_backend

# Simple usage
store = get_vector_store()
backend_name = get_backend()
```

## Interfaces

All database implementations must inherit from these abstract base classes:

### Core Interfaces

| Interface | Purpose | Key Methods |
|-----------|---------|-------------|
| `DatabaseConnection` | Connection lifecycle | `connect()`, `close()` |
| `SchemaManager` | Schema creation | `create_schema()` |
| `VectorStore` | High-level facade | `add_document()`, `search()`, `delete_document()` |

### Repository Interfaces

| Interface | Purpose | Key Methods |
|-----------|---------|-------------|
| `DocumentRepository` | Document CRUD | `add()`, `find_by_path()`, `delete()` |
| `ChunkRepository` | Chunk CRUD | `add()`, `get_by_document()`, `count()` |
| `VectorChunkRepository` | Vector embeddings | `add()`, `add_batch()` |
| `FTSChunkRepository` | Full-text search | `add()`, `search()` |
| `SearchRepository` | Vector similarity | `vector_search()` |
| `GraphRepository` | Knowledge graph | `add_node()`, `add_edge()` |

### Type Hints

Use interfaces for type hints to keep code backend-agnostic:

```python
from ingestion import VectorStoreInterface, DatabaseFactory

def process_documents(store: VectorStoreInterface) -> None:
    # Works with any backend
    store.add_document(path, hash_val, chunks, embeddings)


# Create with factory, type-checked against interface
store: VectorStoreInterface = DatabaseFactory.create_vector_store()
process_documents(store)
```

## Adding a New Backend

To add a new database backend (e.g., MySQL, MongoDB):

### 1. Create Implementation Files

```python
# api/ingestion/mysql_connection.py
from ingestion.interfaces import DatabaseConnection, SchemaManager

class MySQLConnection(DatabaseConnection):
    def connect(self) -> Any:
        # Implementation
        pass

    def close(self) -> None:
        # Implementation
        pass

class MySQLSchemaManager(SchemaManager):
    def create_schema(self) -> None:
        # Implementation
        pass
```

### 2. Implement VectorStore

```python
# api/ingestion/mysql_database.py
from ingestion.interfaces import VectorStore

class MySQLVectorStore(VectorStore):
    def add_document(self, file_path, file_hash, chunks, embeddings) -> None:
        # Implementation
        pass

    def search(self, query_embedding, top_k=5, threshold=None,
               query_text=None, use_hybrid=True) -> List[Dict]:
        # Implementation
        pass

    # ... implement all abstract methods
```

### 3. Register in Factory

Update `database_factory.py`:

```python
@staticmethod
def create_vector_store(config=None, backend=None) -> VectorStore:
    # ... existing code ...

    elif backend == 'mysql':
        from .mysql_database import MySQLVectorStore
        return MySQLVectorStore(config)
```

### 4. Update Detection Logic

```python
@staticmethod
def detect_backend(config) -> BackendType:
    db_url = getattr(config, 'database_url', '')

    if db_url.startswith('mysql://'):
        return 'mysql'
    # ... existing checks
```

## Backend Comparison

| Feature | PostgreSQL + pgvector | SQLite + vectorlite |
|---------|----------------------|---------------------|
| ACID compliance | Full | Limited (WAL mode) |
| Concurrent access | Native | File-level locking |
| ARM64 support | Yes | Requires compilation |
| Server required | Yes | No |
| Setup complexity | Medium | Low |
| Performance (50k vectors) | ~1ms query | ~5ms query |
| Crash recovery | Automatic | Manual |

## Configuration

### PostgreSQL Configuration

```python
@dataclass
class DatabaseConfig:
    database_url: str = "postgresql://ragkb:ragkb@localhost:5432/ragkb"
    host: str = "localhost"
    port: int = 5432
    user: str = "ragkb"
    password: str = "ragkb"
    database: str = "ragkb"
    embedding_dim: int = 384
```

### SQLite Configuration (Legacy)

```python
@dataclass
class DatabaseConfig:
    path: str = "/app/data/rag.db"
    embedding_dim: int = 384
    check_same_thread: bool = False
```

## Migration

### PostgreSQL to SQLite

```bash
# Export data
pg_dump -h localhost -U ragkb ragkb > backup.sql

# Set SQLite backend
export DATABASE_URL=sqlite:///app/data/rag.db

# Re-index documents
# (SQLite schema created automatically on first run)
```

### SQLite to PostgreSQL

Use the migration script:

```bash
python scripts/migrate_to_postgres.py
```

This migrates documents, chunks, vectors, and FTS data.

## Volume Management

### Understanding Docker Volumes

PostgreSQL data is stored in a Docker named volume:

```yaml
volumes:
  rag_kb_postgres_data:  # Named volume
```

Docker prefixes this with the project name, resulting in:
- Volume name: `rag-kb_rag_kb_postgres_data`
- Location: `/var/lib/docker/volumes/rag-kb_rag_kb_postgres_data/_data`

**WARNING**: `docker-compose down -v` deletes ALL volumes including your data!

```bash
# Safe - preserves data
docker-compose down

# DANGEROUS - deletes all data!
docker-compose down -v  # NEVER use unless intentional
```

### Export PostgreSQL Data

Export your knowledge base to `data/ragkb_backup.sql`:

```bash
# Using the backup script (recommended)
./scripts/backup_postgres.sh

# Or with compression for transfer
./scripts/backup_postgres.sh --compress
```

The backup file is stored in `data/` and can be synced across machines.

### Import PostgreSQL Data

Import works for both **fresh installs** and **incremental updates** (replaces existing data):

```bash
# On new machine: clone and start PostgreSQL first
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
docker-compose up -d postgres
sleep 15

# Import the backup (works even if database already has data)
./scripts/restore_postgres.sh

# Or specify a backup file
./scripts/restore_postgres.sh data/ragkb_backup.sql.gz

# Start full stack
docker-compose up -d
curl http://localhost:8000/health
```

### Sync Workflow (Multiple Machines)

```bash
# On source machine: export
./scripts/backup_postgres.sh

# Transfer data/ directory (contains ragkb_backup.sql)
rsync -av data/ user@newmachine:~/rag-kb/data/

# On target machine: import (replaces existing data)
./scripts/restore_postgres.sh
```

### Alternative: Export Volume Directly

For full volume backup (preserves PostgreSQL internals):

```bash
# Export volume to tar
docker run --rm \
  -v rag-kb_rag_kb_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar cvf /backup/postgres_volume.tar /data

# Transfer and import on new machine
docker run --rm \
  -v rag-kb_rag_kb_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar xvf /backup/postgres_volume.tar -C /
```

### Check Volume Status

```bash
# List all volumes
docker volume ls | grep rag

# Inspect volume details
docker volume inspect rag-kb_rag_kb_postgres_data

# Check volume size
docker system df -v | grep rag
```

## Troubleshooting

### Backend Detection Issues

```python
from ingestion import DatabaseFactory

# Check what backend is detected
info = DatabaseFactory.get_backend_info()
print(f"Backend: {info['backend']}")
print(f"Available: {info['available']}")
```

### Import Errors

If you see `SQLite backend not available`:
- Ensure vectorlite is installed: `pip install vectorlite`
- Check platform compatibility (ARM64 may have issues)

If you see `PostgreSQL backend not available`:
- Ensure psycopg2 is installed: `pip install psycopg2-binary`
- Check PostgreSQL server is running

### Migration Issues

**vectorlite knn_search returns 0 results**:
The migration script uses iterative queries with k=5000 because large k values
fail silently in vectorlite. If you see 0 vectors migrated, check:
- HNSW index file exists: `ls -la data/vec_chunks.idx`
- Index is not corrupted: should be ~200MB for 50k vectors
- Use backup if needed: `cp data/vec_chunks.idx.backup data/vec_chunks.idx`

**Volume was accidentally deleted**:
If `docker-compose down -v` was run, you must re-run migration from SQLite backups:
```bash
# Restore SQLite backups
cp data/rag.db.backup data/rag.db
cp data/vec_chunks.idx.backup data/vec_chunks.idx

# Re-run migration
python scripts/migrate_to_postgres.py
```
