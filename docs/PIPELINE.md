# Pipeline Configuration

Configure the ML pipeline: models, chunking, and reranking.

> **For infrastructure settings** (ports, memory, security), see [CONFIGURATION.md](CONFIGURATION.md).
> **For custom implementations**, see [EXTENDING.md](EXTENDING.md).

---

## Quick Start

```bash
# Default CPU configuration
docker-compose up
```

To customize, edit `config/pipeline.yaml`:

```yaml
extraction:
  provider: docling

chunking:
  strategy: hybrid
  max_tokens: 512

embedding:
  provider: sentence-transformers
  model: Snowflake/snowflake-arctic-embed-l-v2.0
  batch_size: 32

reranking:
  enabled: false  # ** Requires GPU (20x slower on CPU)
  model: BAAI/bge-reranker-large
  top_n: 20
```

---

## Configuration Options

### Extraction

| Option | Default | Description |
|--------|---------|-------------|
| `provider` | `docling` | Extraction engine |

### Chunking

| Option | Default | Description |
|--------|---------|-------------|
| `strategy` | `hybrid` | Chunking strategy: `hybrid`, `semantic`, `fixed` |
| `max_tokens` | `512` | Maximum tokens per chunk |

### Embedding

| Option | Default | Description |
|--------|---------|-------------|
| `provider` | `sentence-transformers` | Embedding provider |
| `model` | `Snowflake/snowflake-arctic-embed-l-v2.0` | Model name |
| `batch_size` | `32` | Batch size for encoding |

### Reranking

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `false` | Enable reranking (** **GPU required**) |
| `model` | `BAAI/bge-reranker-large` | Reranker model |
| `top_n` | `20` | Candidates to rerank |

> ** **GPU REQUIRED**: Reranking uses cross-encoder models that are ~20x slower on CPU (~20s vs ~1s per query). Keep disabled for CPU-only builds.

---

## Environment Overrides

All settings can be overridden via environment variables:

```bash
export CHUNK_STRATEGY=semantic
export CHUNK_MAX_TOKENS=256
export EMBEDDING_BATCH_SIZE=16
export RERANKING_ENABLED=false
```

---

## Hardware Profiles

### CPU-Only Build (Default)

For machines without GPU. Uses PostgreSQL pgvector HNSW index for fast queries.

```yaml
# config/pipeline.yaml (default)
reranking:
  enabled: false
```

```bash
# .env
RERANKING_ENABLED=false  # Default
```

**Performance** (benchmarked on 16-core/30GB, 59K vectors):
- Startup: ~2-3s (PostgreSQL + pgvector HNSW index)
- Query latency: **~10-200ms** (depends on embedding model cold start)
- Retrieval quality: Good (vector similarity + query decomposition)
- Suitable for: Development, single-user, production without GPU

> **Note**: Query decomposition is enabled by default, automatically breaking compound queries ("X and Y") into sub-queries for better recall. This adds ~80% latency overhead but improves relevance scores by ~2-6%.

### GPU Build

For machines with NVIDIA GPU. Enables reranking for ~20-30% better retrieval.

```yaml
# config/pipeline.yaml
reranking:
  enabled: true
  model: BAAI/bge-reranker-large
  top_n: 20
```

```bash
# .env
RERANKING_ENABLED=true
```

**Performance** (with GPU acceleration):
- Startup: ~5s (PostgreSQL + pgvector HNSW + reranker model)
- Query latency: **~1-2 seconds** (GPU-accelerated reranking)
- Retrieval quality: Excellent (+20-30% vs CPU-only)
- Suitable for: Production, multi-agent, high-volume

> ** **CPU Warning**: Reranking on CPU takes ~20 seconds per query. Only enable with GPU.

### Pre-configured Profiles

Available in `config/profiles/`:

| Profile | Use Case | Reranking |
|---------|----------|-----------|
| `cpu-only.yaml` | Default, works everywhere | Disabled |
| `rtx3060.yaml` | 12GB VRAM GPU | Enabled |
| `rtx4080.yaml` | 16GB VRAM GPU | Enabled |

### Using Profiles

```bash
cp config/profiles/cpu-only.yaml config/pipeline.yaml
docker-compose restart rag-api
```

---

## Pipeline Flow

```
INGESTION:
Document → Extract → Chunk → Embed → Store

QUERY:
Query → Embed → Search → Rerank → Results
```

---

## See Also

- [EXTENDING.md](EXTENDING.md) - Add custom implementations
- [CONFIGURATION.md](CONFIGURATION.md) - Infrastructure settings
