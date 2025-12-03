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
  enabled: true
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
| `enabled` | `true` | Enable reranking |
| `model` | `BAAI/bge-reranker-large` | Reranker model |
| `top_n` | `20` | Candidates to rerank |

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

Pre-configured profiles in `config/profiles/`:

| Profile | Use Case |
|---------|----------|
| `cpu-only.yaml` | Default, works everywhere |
| `rtx3060.yaml` | 12GB VRAM GPU |
| `rtx4080.yaml` | 16GB VRAM GPU |

### Using Profiles

```bash
cp config/profiles/cpu-only.yaml config/pipeline.yaml
docker-compose restart api
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
