# Configuration Guide

This guide covers all configuration options for RAG-KB.

## Table of Contents

- [Hardware Requirements](#hardware-requirements)
- [Configuration via .env](#configuration-via-env)
  - [Troubleshooting Configuration Issues](#troubleshooting-configuration-issues)
  - [Common Configuration Mistakes](#common-configuration-mistakes)
- [Knowledge Base Directory](#knowledge-base-directory)
- [Resource Limits](#resource-limits)
- [Embedding Models](#embedding-models)
- [Concurrent Processing](#concurrent-processing)
- [Auto-Sync Configuration](#auto-sync-configuration)
- [Hybrid Search Configuration](#hybrid-search-configuration)
- [Query Caching Configuration](#query-caching-configuration)
- [Chunking Configuration](#chunking-configuration)
- [Performance Stats](#performance-stats)
- [Resource Profiles](#resource-profiles)

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

RAG-KB uses a **single source of truth** configuration pattern:

| Location | Purpose | Edit? |
|----------|---------|-------|
| `.env` | **User customization** | ✅ Yes - edit this file |
| `docker-compose.yml` | Factory defaults | ❌ No - don't edit unless adding new features |
| Python code | Reads from environment | ❌ No - no hardcoded defaults |

### How it works

1. `docker-compose.yml` defines **sane defaults** using `${VAR:-default}` syntax
2. Docker Compose auto-loads `.env` from project root (if it exists)
3. Values in `.env` override the defaults in `docker-compose.yml`
4. Container receives final merged environment variables
5. Python code reads from `os.environ` - no fallback defaults

**Key principle:** Only edit `.env` for customization. The defaults in `docker-compose.yml` work for most users.

### Example .env file

```bash
# Only override what you need to change
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
RAG_PORT=8001
MAX_MEMORY=8G
EMBEDDING_WORKERS=2
```

All other settings (batch size, cache config, chunking, etc.) will use the defaults from `docker-compose.yml`.

**See `.env.example` for all available options with documentation.**

### Troubleshooting Configuration Issues

If settings aren't taking effect:

**1. Check your `.env` file exists and has correct syntax:**
```bash
# View current .env
cat .env

# Check for syntax errors (no spaces around =)
# GOOD: MAX_CPUS=4.0
# BAD:  MAX_CPUS = 4.0
```

**2. Verify the container sees your settings:**
```bash
# Check what the container actually received
docker exec rag-api env | grep -E "MAX_CPUS|MAX_MEMORY|EMBEDDING"
```

**3. Restart after changes:**
```bash
# .env changes require restart (not rebuild)
docker-compose restart rag-api

# docker-compose.yml changes require recreate
docker-compose up -d
```

**4. Check for shell environment overrides:**
```bash
# Shell exports override .env! Check for conflicts:
env | grep -E "MAX_CPUS|MODEL_NAME|EMBEDDING"

# If found, unset them:
unset MAX_CPUS MAX_MEMORY MODEL_NAME
```

**5. Validate docker-compose sees your .env:**
```bash
# Shows merged config with your .env values applied
docker-compose config | grep -A5 "environment:"
```

### Common Configuration Mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Settings ignored | Spaces around `=` in .env | Remove spaces: `MAX_CPUS=4.0` |
| Old values persist | Forgot to restart | `docker-compose restart rag-api` |
| Different than expected | Shell export overriding | `unset VAR_NAME` before docker-compose |
| Works locally, not in Docker | Path not mounted | Check volumes in docker-compose.yml |

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
MAX_CPUS=4.0          # Max CPU cores (default: 4.0)
MAX_MEMORY=8G         # Max memory usage (default: 8G)
BATCH_SIZE=5          # Files per batch (default: 5)
BATCH_DELAY=0.5       # Delay between batches in seconds (default: 0.5)
```

**Note:** The defaults in `docker-compose.yml` are tuned for the **Balanced profile on an 8-core, 16GB system**. See [Resource Profiles](#resource-profiles) to find values for your hardware.

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
CHUNK_WORKERS=2          # Number of parallel chunking threads (default: 2)
EMBEDDING_WORKERS=2      # Number of parallel embedding threads (default: 2)
EMBEDDING_BATCH_SIZE=32  # Chunks per batch (default: 32)
```

**Why 2 workers?** Python's GIL (Global Interpreter Lock) serializes CPU-bound model inference. More workers don't help - they compete for the GIL. Instead, we use batch encoding (EMBEDDING_BATCH_SIZE=32) for 10-50x throughput gains.

### Performance Benefits

- **Before v1.7.0**: ~2 files/hour for large PDFs (one-at-a-time encoding)
- **After v1.7.0**: ~20-100 files/hour (batch encoding with BatchEncoder class)

### Important: Don't Increase Worker Counts

Adding more workers **does not improve performance** due to GIL contention:

```bash
# BAD - workers fight for GIL, no speedup
EMBEDDING_WORKERS=6   # Don't do this

# GOOD - batch encoding gives real speedup
EMBEDDING_WORKERS=2
EMBEDDING_BATCH_SIZE=32
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
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0  # Default: multilingual, best quality
EMBEDDING_DIMENSION=1024

# Port configuration
RAG_PORT=8000

# Resource limits (defaults tuned for 8-core, 16GB Balanced profile)
MAX_CPUS=4.0
MAX_MEMORY=8G
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
EMBEDDING_WORKERS=2
MAX_CPUS=4.0
MAX_MEMORY=8G
CACHE_MAX_SIZE=200
```

### Example 2: High-Quality Multilingual Setup

Best quality for diverse content:

```bash
# .env
MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0
EMBEDDING_WORKERS=2
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
EMBEDDING_WORKERS=1
BATCH_SIZE=2
BATCH_DELAY=2.0
CACHE_ENABLED=false
```

## Resource Profiles

RAG-KB can be tuned for different usage scenarios. Use these profiles based on whether you need your machine responsive for other tasks.

### Step 1: Detect Your Hardware

Run these commands to get your system specs:

**Linux/WSL:**
```bash
# CPU cores (logical) - uses /proc/cpuinfo for accurate count
# Note: `nproc` can report incorrect values in containers/cgroups
grep -c processor /proc/cpuinfo

# Total RAM in GB
free -g | awk '/^Mem:/{print $2}'

# Or combined:
echo "CPU cores: $(grep -c processor /proc/cpuinfo), RAM: $(free -g | awk '/^Mem:/{print $2}')GB"

# Detailed CPU info (physical cores, threads per core)
lscpu | grep -E "^CPU\(s\):|^Thread|^Core"
```

**macOS:**
```bash
# CPU cores
sysctl -n hw.ncpu

# Total RAM in GB
echo $(($(sysctl -n hw.memsize) / 1024 / 1024 / 1024))

# Or combined:
echo "CPU cores: $(sysctl -n hw.ncpu), RAM: $(($(sysctl -n hw.memsize) / 1024 / 1024 / 1024))GB"
```

### Step 2: Choose Your Profile

#### Profile A: Balanced (50-60% resources)

**Use when:** Running backtesting, development work, or other CPU-intensive tasks alongside RAG-KB. Device stays responsive.

| Your Hardware | MAX_CPUS | MAX_MEMORY | EMBEDDING_WORKERS | CHUNK_WORKERS | OMP_NUM_THREADS |
|--------------|----------|------------|-------------------|---------------|-----------------|
| 4 cores, 8GB | 2.0 | 4G | 1 | 1 | 1 |
| 8 cores, 16GB | 4.0 | 8G | 2 | 1 | 2 |
| 12 cores, 32GB | 6.0 | 16G | 2 | 1 | 2 |
| 16 cores, 32GB | 8.0 | 16G | 2 | 1 | 3 |
| 16 cores, 64GB | 8.0 | 32G | 2 | 1 | 3 |

**Example .env for 8 cores, 16GB (Balanced):**
```bash
MAX_CPUS=4.0
MAX_MEMORY=8G
EMBEDDING_WORKERS=2
EMBEDDING_BATCH_SIZE=32
CHUNK_WORKERS=1
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
```

#### Profile B: Performance (70-80% resources)

**Use when:** Dedicated indexing sessions where you don't mind some system lag. Faster processing, especially for initial large imports.

| Your Hardware | MAX_CPUS | MAX_MEMORY | EMBEDDING_WORKERS | CHUNK_WORKERS | OMP_NUM_THREADS |
|--------------|----------|------------|-------------------|---------------|-----------------|
| 4 cores, 8GB | 3.0 | 6G | 2 | 1 | 2 |
| 8 cores, 16GB | 6.0 | 12G | 2 | 1 | 2 |
| 12 cores, 32GB | 9.0 | 24G | 2 | 2 | 3 |
| 16 cores, 32GB | 12.0 | 24G | 2 | 2 | 4 |
| 16 cores, 64GB | 12.0 | 48G | 2 | 2 | 4 |

**Note:** Workers stay at 2 due to GIL limitations (see below). More CPU budget goes to `OMP_NUM_THREADS` for NumPy/BLAS parallelism which releases the GIL.

**Example .env for 8 cores, 16GB (Performance):**
```bash
MAX_CPUS=6.0
MAX_MEMORY=12G
EMBEDDING_WORKERS=2
EMBEDDING_BATCH_SIZE=32
CHUNK_WORKERS=1
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
```

### Step 3: Apply Configuration

```bash
# Create or edit .env with your chosen profile
cat > .env << 'EOF'
# Your chosen settings here
MAX_CPUS=4.0
MAX_MEMORY=8G
EMBEDDING_WORKERS=2
EMBEDDING_BATCH_SIZE=32
CHUNK_WORKERS=1
EOF

# Restart to apply
docker-compose down && docker-compose up -d
```

### Understanding the Settings

| Setting | What it controls | Impact |
|---------|-----------------|--------|
| `MAX_CPUS` | Docker CPU limit | Higher = faster but less responsive |
| `MAX_MEMORY` | Docker RAM limit | Higher = more concurrent processing |
| `EMBEDDING_WORKERS` | Parallel embedding threads | More workers ≠ faster (see below) |
| `EMBEDDING_BATCH_SIZE` | Chunks per model call | 32 optimal for CPU, higher uses more RAM |
| `CHUNK_WORKERS` | Parallel chunking threads | Keep at 1-2 (see below) |
| `OMP_NUM_THREADS` | NumPy/BLAS parallelism | 2 is usually optimal, higher causes contention |

### Why More Workers Don't Always Help (GIL Contention)

Python's Global Interpreter Lock (GIL) means only ONE thread can execute Python code at a time, regardless of CPU cores. This fundamentally affects our pipeline:

| Stage | Nature | Recommended | Why |
|-------|--------|-------------|-----|
| **Chunking** | I/O + CPU (Docling) | 1-2 | File I/O overlaps, but parsing is CPU-bound |
| **Embedding** | Pure CPU-bound | 1-2 | GIL serializes model inference |
| **Storing** | I/O-bound (SQLite) | 1 | SQLite is single-writer |

**Key insight from High Performance Python**: Adding more workers to CPU-bound stages doesn't help - workers compete for the GIL and hinder each other. Instead:

1. **Batch encoding** (`EMBEDDING_BATCH_SIZE=32`) gives 10-50x speedup by reducing `model.encode()` calls
2. **Fewer workers with larger batches** beats many workers fighting for GIL
3. **OMP_NUM_THREADS=2** lets NumPy use 2 cores per worker for matrix ops (releases GIL)

**Recommended allocation for 80% CPU budget:**

```
Stage        Workers   Nature              CPU Usage
─────────────────────────────────────────────────────
Chunking     1         I/O + CPU           ~1 core (overlaps with embedding I/O)
Embedding    2         CPU-bound (GIL)     ~1 active + 2 OMP threads = ~3 cores
Storing      1         I/O-bound           minimal (SQLite writes)
─────────────────────────────────────────────────────
Total effective usage: ~4 cores (good for 8-core @ 50%)
```

**Why not more embedding workers?**
- 2 workers: One waits for GIL while other runs → some overlap during I/O
- 4 workers: Three waiting, one running → wasted memory, no speed gain
- The GIL means `EMBEDDING_WORKERS=2` is usually optimal for CPU builds

### Quick Reference: Formulas

For a quick estimate based on your hardware:

**Balanced (50-60%):**
- `MAX_CPUS` = cores × 0.5
- `MAX_MEMORY` = RAM × 0.5
- `EMBEDDING_WORKERS` = max(1, cores ÷ 4)

**Performance (70-80%):**
- `MAX_CPUS` = cores × 0.75
- `MAX_MEMORY` = RAM × 0.75
- `EMBEDDING_WORKERS` = max(2, cores ÷ 3)

### Monitoring Resource Usage

Check if your profile is working:

```bash
# Real-time Docker stats
docker stats rag-api

# One-time snapshot
docker stats rag-api --no-stream
```

Expected output during indexing:
- **Balanced**: CPU ~50-60%, Memory within limit
- **Performance**: CPU ~70-80%, Memory within limit

If CPU is consistently at 100% of your limit, the profile is working as intended.

## Next Steps

- **Quick Start**: See [QUICK_START.md](QUICK_START.md) to get started
- **Usage**: See [USAGE.md](USAGE.md) for query methods
- **Development**: See [DEVELOPMENT.md](DEVELOPMENT.md) for testing and development
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues
