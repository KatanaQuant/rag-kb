# Configuration Guide

Infrastructure settings for RAG-KB.

> **For ML pipeline settings** (models, chunking, reranking), see [PIPELINE.md](PIPELINE.md).

---

## Quick Start

```bash
# Copy example config
cp .env.example .env

# Edit as needed
nano .env

# Restart to apply
docker-compose restart api
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Infrastructure: ports, memory, workers, security |
| `config/pipeline.yaml` | ML Pipeline: models, chunking, reranking |

---

## Hardware Requirements

### Minimum
- **RAM**: 4GB
- **CPU**: 2 cores
- **Storage**: SATA SSD, 500MB + 2x knowledge base size

### Recommended
- **RAM**: 16GB
- **CPU**: 8-16 cores
- **Storage**: NVMe SSD

---

## Core Settings

### Ports

```bash
RAG_PORT=8000
```

### Resources

```bash
MAX_CPUS=4          # Docker CPU limit
MAX_MEMORY=8G       # Docker memory limit
```

### Workers

```bash
EMBEDDING_WORKERS=2      # Parallel embedding threads
CHUNK_WORKERS=1          # Parallel chunking threads
EMBEDDING_BATCH_SIZE=32  # Chunks per batch
```

> **Note**: More workers don't help due to Python GIL. Use batch encoding instead.

---

## Knowledge Base Path

```bash
# Default: ./kb/
KB_PATH=/path/to/your/documents
```

For paths outside project directory, update `docker-compose.yml`:

```yaml
volumes:
  - /your/path:/app/kb
```

---

## Auto-Sync

```bash
WATCH_ENABLED=true           # Enable file watching
WATCH_DEBOUNCE_SECONDS=10.0  # Wait after last change
WATCH_BATCH_SIZE=50          # Max files per batch
```

---

## Query Cache

```bash
CACHE_ENABLED=true   # Enable LRU cache
CACHE_MAX_SIZE=100   # Max cached queries
```

---

## Resource Profiles

### Balanced (50-60% resources)

For running alongside other tasks:

| Hardware | MAX_CPUS | MAX_MEMORY | WORKERS |
|----------|----------|------------|---------|
| 4 cores, 8GB | 2 | 4G | 1 |
| 8 cores, 16GB | 4 | 8G | 2 |
| 16 cores, 32GB | 8 | 16G | 2 |

### Performance (70-80% resources)

For dedicated indexing:

| Hardware | MAX_CPUS | MAX_MEMORY | WORKERS |
|----------|----------|------------|---------|
| 4 cores, 8GB | 3 | 6G | 2 |
| 8 cores, 16GB | 6 | 12G | 2 |
| 16 cores, 32GB | 12 | 24G | 2 |

---

## Environment Variables Reference

### Core

```bash
RAG_PORT=8000
MAX_CPUS=4
MAX_MEMORY=8G
```

### Workers

```bash
CHUNK_WORKERS=1
EMBEDDING_WORKERS=2
EMBEDDING_BATCH_SIZE=32
```

### Batching

```bash
BATCH_SIZE=5
BATCH_DELAY=0.5
```

### Auto-Sync

```bash
WATCH_ENABLED=true
WATCH_DEBOUNCE_SECONDS=10.0
WATCH_BATCH_SIZE=50
```

### Cache

```bash
CACHE_ENABLED=true
CACHE_MAX_SIZE=100
```

---

## Troubleshooting

### Settings Not Taking Effect

```bash
# Check container sees your settings
docker exec rag-api env | grep MAX_CPUS

# Restart after .env changes
docker-compose restart api
```

### Common Mistakes

| Problem | Cause | Fix |
|---------|-------|-----|
| Settings ignored | Spaces around `=` | `MAX_CPUS=4` not `MAX_CPUS = 4` |
| Old values | Forgot restart | `docker-compose restart rag-api` |
| Shell override | `export` in shell | `unset VAR_NAME` |

### Shell Exports Override .env

Shell environment variables take precedence over `.env` values. If your settings aren't applying:

```bash
# Check for shell overrides
env | grep -E "MAX_CPUS|MAX_MEMORY"

# Clear them
unset MAX_CPUS MAX_MEMORY OMP_NUM_THREADS MKL_NUM_THREADS

# Recreate container (required for resource limit changes)
docker-compose down && docker-compose up -d
```

> **Note**: `docker-compose restart` works for most settings, but resource limits (`MAX_CPUS`, `MAX_MEMORY`) require `down && up` to take effect.

---

## Detect Your Hardware

**Linux:**
```bash
echo "CPU: $(grep -c processor /proc/cpuinfo), RAM: $(free -g | awk '/^Mem:/{print $2}')GB"
```

**macOS:**
```bash
echo "CPU: $(sysctl -n hw.ncpu), RAM: $(($(sysctl -n hw.memsize) / 1024 / 1024 / 1024))GB"
```

---

## See Also

- [PIPELINE.md](PIPELINE.md) - ML pipeline configuration
- [QUICK_START.md](QUICK_START.md) - Getting started
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues
