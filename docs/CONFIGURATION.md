# Configuration Guide

This guide covers all configuration options for RAG-KB.

## Table of Contents

- [Hardware Requirements](#hardware-requirements)
- [Configuration via .env](#configuration-via-env)
- [Knowledge Base Directory](#knowledge-base-directory)
- [Resource Limits](#resource-limits)
- [Embedding Models](#embedding-models)
- [Concurrent Processing](#concurrent-processing)
- [Auto-Sync Configuration](#auto-sync-configuration)
- [Hybrid Search Configuration](#hybrid-search-configuration)
- [Query Caching Configuration](#query-caching-configuration)
- [Chunking Configuration](#chunking-configuration)
- [Performance Stats](#performance-stats)

## Hardware Requirements

### CPU-Only (Production-Ready)

- **RAM**: 4-8GB minimum (16GB recommended for large KB)
- **CPU**: 2+ cores (4+ recommended)
- **Storage**: 500MB + (2x knowledge base size)
- **Processing**: 10-500 docs/hour depending on format and model choice

### Recommended Setup

- 8-16 CPU cores for faster parallel processing
- 16GB RAM for comfortable large knowledge base indexing
- SSD storage for faster database I/O

**Note:** This project is CPU-only by design. No GPU support is planned.

## Configuration via .env

RAG-KB uses a two-tier configuration approach:

1. **docker-compose.yml**: Provides sensible defaults for all settings
2. **.env file**: Optional overrides for customization (you only specify what you want to change)

### How it works

- Docker Compose automatically loads `.env` from the project root
- Any variable in `.env` overrides the corresponding default in `docker-compose.yml`
- If `.env` doesn't exist or a variable is missing, the default is used

### Example .env file

```bash
# Only override what you need to change
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
RAG_PORT=8001
MAX_MEMORY=8G
EMBED_WORKERS=6
```

All other settings (batch size, cache config, chunking, etc.) will use the defaults from `docker-compose.yml`.

**See `.env.example` for all available options with documentation.**

## Knowledge Base Directory

By default, RAG-KB looks for documents in `./knowledge_base/` directory. You can customize this location using the `KNOWLEDGE_BASE_PATH` environment variable.

### Configuration

Edit `.env`:

```bash
# Use a custom knowledge base directory
KNOWLEDGE_BASE_PATH=/path/to/your/documents
```

### Examples

**External drive**:
```bash
KNOWLEDGE_BASE_PATH=/media/external_drive/my_knowledge_base
```

**Home directory**:
```bash
KNOWLEDGE_BASE_PATH=~/Documents/knowledge_base
```

**Network storage**:
```bash
KNOWLEDGE_BASE_PATH=/mnt/nas/documents
```

### Important Notes

1. **Path expansion**: The `~` character is automatically expanded to your home directory
2. **Relative paths**: Relative paths are converted to absolute paths
3. **Docker access**: For paths outside the project directory, you need to update `docker-compose.yml`:

```yaml
services:
  rag-api:
    volumes:
      - ./data:/app/data
      - /your/custom/path:/app/knowledge_base  # Update this line
```

Or use an environment variable in `docker-compose.yml`:

```yaml
services:
  rag-api:
    volumes:
      - ./data:/app/data
      - ${KB_MOUNT_PATH:-./knowledge_base}:/app/knowledge_base
```

Then in `.env`:
```bash
KB_MOUNT_PATH=/your/custom/path
```

### Use Cases

- **Point to existing collections**: Index documents without copying them
- **Multiple drives**: Store knowledge base on faster/larger storage
- **Network attached storage (NAS)**: Access centralized document repository
- **Multiple knowledge bases**: Switch between different document collections

### Default Behavior

If `KNOWLEDGE_BASE_PATH` is not set, the default location is `/app/knowledge_base` inside the Docker container, which maps to `./knowledge_base/` in your project directory.

## Resource Limits

To prevent system overload during large indexing operations, RAG-KB includes resource caps.

### Configuration

Edit `.env`:

```bash
MAX_CPUS=2.0          # Max CPU cores (default: 2.0)
MAX_MEMORY=4G         # Max memory usage (default: 4G)
BATCH_SIZE=5          # Files per batch (default: 5)
BATCH_DELAY=0.5       # Delay between batches in seconds (default: 0.5)
```

### How it works

- Docker resource limits prevent container from exceeding CPU/memory caps
- Batch processing adds delays every N files to prevent resource spikes
- Ideal for laptops and devices with limited resources

### Adjust for your system

**Low-end device (2GB RAM, 2 cores)**:
```bash
echo "MAX_MEMORY=2G" >> .env
echo "MAX_CPUS=1.0" >> .env
echo "BATCH_SIZE=3" >> .env

docker-compose up --build -d
```

**High-end device (16GB RAM, 8 cores)**:
```bash
echo "MAX_MEMORY=8G" >> .env
echo "MAX_CPUS=4.0" >> .env
echo "BATCH_SIZE=10" >> .env
echo "BATCH_DELAY=0.1" >> .env

docker-compose up --build -d
```

## Embedding Models

v0.2.0+ supports multiple embedding models for different quality/speed/resource trade-offs.

### Available Models

| Model | Dimensions | Memory | MTEB Score | Speed | Use Case |
|-------|-----------|--------|------------|-------|----------|
| all-MiniLM-L6-v2 | 384 | ~80MB | Good | Very Fast | Quick prototyping, simple queries |
| **static-retrieval-mrl-en-v1** | 1024 | **~400MB** | ~87% of mpnet | **100-400x faster** | **CPU-optimized, English-only, recommended** |
| Arctic Embed 2.0-M | 768 | ~450MB | 55.4 (Retrieval) | Very Fast | Balanced quality/speed |
| Arctic Embed 2.0-L | 1024 | ~1.2GB | **55.6 (Retrieval)** | Fast | Best retrieval quality, multilingual |
| BGE-base-en-v1.5 | 768 | ~450MB | Very Good | Fast | Lightweight alternative |
| BGE-large-en-v1.5 | 1024 | ~1.3GB | 64.2 (Avg) / 54.3 (Retrieval) | Medium | Alternative high-quality option |

### Recommended Configurations

**CPU-Optimized (Recommended for v0.4+)**:
```bash
# 66% less memory, 100-400x faster, English-only, 13% quality trade-off
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1
```

**Production (Multilingual)**:
```bash
# Best retrieval quality, multilingual, slower processing
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
```

### To change models

```bash
# Create/edit .env file
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env

# Rebuild with new model (requires re-indexing)
docker-compose down
rm data/rag.db
docker-compose up --build -d
```

### Model Tradeoffs

| Factor | static-retrieval-mrl (Recommended) | Arctic 2.0-L |
|--------|-----------------------------------|--------------|
| **Quality** | Good (~87% of mpnet) | Excellent (55.6 MTEB Retrieval) |
| **Speed** | 100-400x faster | Fast |
| **Memory** | 400MB (66% less) | 1.2GB |
| **Multilingual** | English only | Yes (100+ languages) |
| **Use Case** | CPU builds, English content | Multilingual, GPU builds |

### Performance Notes

- **static-retrieval-mrl**: Static embeddings (no neural network inference), extreme speed, minimal memory, ideal for CPU-only deployments
- **Arctic Embed 2.0-L**: Best-in-class retrieval (55.6 MTEB), multilingual support, ideal for diverse content with GPU acceleration
- **Model download**: Models download once and are cached thereafter
- **Re-indexing required**: Different dimensions = incompatible database format

For model testing and migration workflows, see [DEVELOPMENT.md](DEVELOPMENT.md#testing-new-models-without-disrupting-production).

## Concurrent Processing

v0.11.0+ implements a 3-stage concurrent pipeline for faster document processing.

### Architecture

```
IndexingQueue (Priority) → IndexingWorker → PipelineCoordinator
                                              ↓
                                      ChunkWorker (1 thread)
                                              ↓
                                      EmbedWorkerPool (2 threads, CPU default)
                                              ↓
                                      StoreWorker (1 thread)
```

### Configuration

Edit `.env`:

```bash
CHUNK_WORKERS=1          # Number of parallel chunking threads (default: 1)
EMBEDDING_WORKERS=2      # Number of parallel embedding threads (default: 2)
```

**CPU vs GPU builds**: The default of 2 embedding workers is optimized for CPU-only builds. CPU embedding is resource-intensive, and running 3+ concurrent embedding operations can cause slowdowns when using the device for other tasks. For GPU-accelerated builds, increase to 3-6 workers.

### Performance Benefits

- **Before**: ~2 files/hour for large PDFs (sequential processing)
- **After**: ~6-8 files/hour (3-4x improvement with 2 embedding workers)

### Tuning for Your System

**For 8-core machine**:
```bash
echo "EMBED_WORKERS=6" >> .env
docker-compose restart rag-api
```

**For 4-core machine**:
```bash
echo "EMBED_WORKERS=3" >> .env
docker-compose restart rag-api
```

**Performance Notes**:
- Set `CHUNK_WORKERS=2` if processing many large PDFs with OCR
- Single chunk worker prevents resource contention but may bottleneck on slow files
- Multiple chunk workers split CPU resources but process files in parallel

### Priority-Based Queue System

The queue system uses two priority levels:

- **HIGH**: Orphan repair and data integrity operations
- **NORMAL**: New file indexing

**Fast-track a file**:
```bash
curl -X POST "http://localhost:8000/indexing/priority/knowledge_base/important.pdf"
```

See [API.md](API.md) for complete queue management API.

## Auto-Sync Configuration

The system automatically watches for new and modified files in `knowledge_base/` and indexes them without requiring a restart. This happens in real-time with smart debouncing to handle bulk operations efficiently.

### How it works

- File watcher monitors `knowledge_base/` directory recursively
- Changes are collected for 10 seconds (debounce period) to batch operations
- After quiet period, all changes are indexed together
- Handles text editor save patterns, git operations, and bulk file copies gracefully

### Configuration

Edit `.env`:

```bash
WATCH_ENABLED=true                  # Enable/disable auto-sync (default: true)
WATCH_DEBOUNCE_SECONDS=10.0         # Wait time after last change (default: 10.0)
WATCH_BATCH_SIZE=50                 # Max files per batch (default: 50)
```

### Use cases

- **Real-time**: Drop PDFs into `knowledge_base/books/` → indexed automatically
- **Updates**: Modify existing files → changes detected and reindexed
- **Bulk imports**: Copy 100 files → batched into efficient indexing

### To disable auto-sync

For manual control only:

```bash
echo "WATCH_ENABLED=false" >> .env
docker-compose restart rag-api
```

## Hybrid Search Configuration

The system uses **Reciprocal Rank Fusion (RRF)** to combine vector similarity search with FTS5 keyword search, providing 10-30% better accuracy for technical queries.

### How it works

- Vector search finds semantically similar content
- Keyword search (FTS5) finds exact term matches
- RRF algorithm merges and ranks results
- Automatic fallback to vector-only if keyword search fails

### Benefits

- Better recall for technical terms, acronyms, and specific terminology
- Improved precision when query contains both concepts and keywords
- Robust to varying query styles (natural language vs. keyword-based)

Hybrid search is **enabled by default** with no configuration needed. It automatically activates when both vector and keyword indexes are available.

### To disable hybrid search

Fallback to vector-only (not recommended):

```python
# In api/api_services/query_executor.py, modify QueryExecutor._search():
use_hybrid=False  # Change from True to False
```

## Query Caching Configuration

LRU (Least Recently Used) cache for query results, providing instant responses for repeat queries.

### Configuration

Edit `.env`:

```bash
CACHE_ENABLED=true                  # Enable/disable caching (default: true)
CACHE_MAX_SIZE=100                  # Maximum cached queries (default: 100)
```

### How it works

- First query: Normal search (vector + keyword fusion)
- Repeat query: Instant cache hit (0ms latency)
- Cache eviction: Least recently used entries removed when full
- Cache keys: Based on query text, top_k, and threshold

### Benefits

- ~1000x faster for repeat queries
- Reduced embedding computation
- Lower memory usage vs. full result caching

### Use cases

- Development/debugging: Repeated test queries
- Multi-user scenarios: Common questions cached
- Interactive exploration: Refining queries with same base text

### To increase cache size

For high-traffic scenarios:

```bash
echo "CACHE_MAX_SIZE=500" >> .env
docker-compose restart rag-api
```

## Chunking Configuration

### HybridChunker (PDF/DOCX - Recommended)

The system uses HybridChunker for PDF and DOCX files, providing token-aware semantic chunking that preserves document structure while maximizing embedding model capacity utilization.

**Configuration** (via `.env`):
```bash
SEMANTIC_CHUNKING=true        # Enable HybridChunker (default: true)
CHUNK_MAX_TOKENS=512          # Match embedding model capacity (default: 512)
USE_DOCLING=true              # Required for HybridChunker (default: true)
```

### Why HybridChunker?

- **4x better token utilization**: Fills chunks closer to 512-token embedding capacity (vs ~79 tokens with fixed-size)
- **40% fewer chunks**: More efficient storage and faster retrieval
- **Preserves semantics**: Keeps tables, code blocks, paragraphs, and sections intact
- **Better retrieval quality**: Complete concepts improve relevance scores by 10-15%

### Real-world example

**272-page technical book**:
- HybridChunker: 372 chunks averaging 324 tokens each
- Fixed-size: ~1,623 chunks averaging 79 tokens each
- Result: Same content, 77% fewer chunks, 4x better token usage

### Markdown/Text Chunking

For Markdown and text files, the system uses semantic chunking with boundary detection.

To adjust fallback chunking (edit `api/config.py`):
```python
CHUNK_SIZE = 1000      # Characters per chunk
CHUNK_OVERLAP = 200    # Overlap between chunks
```

**For detailed technical explanation**, see [WHY_HYBRIDCHUNKER.md](WHY_HYBRIDCHUNKER.md)

## Port Configuration

### Change Default Port

If port 8000 is in use:

```bash
echo "RAG_PORT=8001" > .env
docker-compose up -d
```

### Network Access

To access from other devices on your network, edit `docker-compose.yml`:

```yaml
ports:
  - "0.0.0.0:8000:8000"  # Listen on all interfaces (default: 127.0.0.1:8000:8000)
```

Then restart:
```bash
docker-compose up -d
```

Access via: `http://YOUR_LOCAL_IP:8000`

**Security Warning**: This exposes your knowledge base to your entire network. Only enable on trusted networks.

## Performance Stats

### Expected Performance

| Database Size | Docs | Chunks | Query Time | Storage |
|--------------|------|--------|-----------|---------|
| Small | <50 | <5k | <50ms | <20MB |
| Medium | 50-500 | 5k-50k | <100ms | 20-200MB |
| Large | 500-1000 | 50k-100k | <500ms | 200MB-1GB |

### Check Stats

```bash
# Database size
du -h data/rag.db

# System health
curl http://localhost:8000/health | jq
```

Example output:
```json
{
  "status": "healthy",
  "indexed_documents": 1588,
  "total_chunks": 36466,
  "model": "Snowflake/snowflake-arctic-embed-l-v2.0",
  "indexing_in_progress": false
}
```

### Monitor Performance

```bash
# Docker resource usage
docker stats rag-api --no-stream

# Query timing
time curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 5}'

# Indexing logs
docker-compose logs rag-api | grep "Indexed"
```

## Environment Variables Reference

### Core Settings

```bash
# Model configuration
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1
EMBEDDING_DIMENSION=1024

# Port configuration
RAG_PORT=8000

# Resource limits
MAX_CPUS=2.0
MAX_MEMORY=4G
```

### Concurrent Processing

```bash
# Worker pools
CHUNK_WORKERS=1
EMBEDDING_WORKERS=2    # 2 for CPU builds, increase for GPU

# Batch processing
BATCH_SIZE=5
BATCH_DELAY=0.5
```

### Auto-Sync

```bash
WATCH_ENABLED=true
WATCH_DEBOUNCE_SECONDS=10.0
WATCH_BATCH_SIZE=50
```

### Caching

```bash
CACHE_ENABLED=true
CACHE_MAX_SIZE=100
```

### Chunking

```bash
SEMANTIC_CHUNKING=true
CHUNK_MAX_TOKENS=512
USE_DOCLING=true
```

### Complete Reference

See `.env.example` for all available options with detailed comments.

## Advanced Configuration

### Custom Docker Build

For advanced users who want to modify the Docker image:

```dockerfile
# Edit Dockerfile
# Add custom dependencies, change base image, etc.
```

Then rebuild:
```bash
docker-compose build --no-cache
docker-compose up -d
```

### Custom Python Dependencies

Add to `api/requirements.txt`:
```
# Your custom packages
my-custom-package==1.0.0
```

Rebuild:
```bash
docker-compose build --no-cache
docker-compose up -d
```

### Database Location

By default, the database is stored in `data/rag.db`. To change location, edit `docker-compose.yml`:

```yaml
volumes:
  - ./custom_data_dir:/app/data
```

## Configuration Examples

### Example 1: Fast English-Only Setup

Optimized for speed with English content:

```bash
# .env
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1
EMBED_WORKERS=6
MAX_CPUS=4.0
MAX_MEMORY=8G
CACHE_MAX_SIZE=200
```

### Example 2: High-Quality Multilingual Setup

Best quality for diverse content:

```bash
# .env
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
EMBED_WORKERS=3
MAX_CPUS=4.0
MAX_MEMORY=8G
BATCH_SIZE=3
BATCH_DELAY=1.0
```

### Example 3: Resource-Constrained Setup

For low-end devices:

```bash
# .env
MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
MAX_CPUS=1.0
MAX_MEMORY=2G
EMBED_WORKERS=1
BATCH_SIZE=2
BATCH_DELAY=2.0
CACHE_ENABLED=false
```

## Next Steps

- **Quick Start**: See [QUICK_START.md](QUICK_START.md) to get started
- **Usage**: See [USAGE.md](USAGE.md) for query methods
- **Development**: See [DEVELOPMENT.md](DEVELOPMENT.md) for testing and development
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
