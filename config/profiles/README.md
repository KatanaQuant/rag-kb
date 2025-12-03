# Hardware Profiles

Pre-configured pipeline settings optimized for different hardware configurations.

## Available Profiles

| Profile | Hardware | VRAM | Use Case |
|---------|----------|------|----------|
| `cpu-only.yaml` | Any CPU | N/A | Default, development, low-cost |
| `rtx3060.yaml` | RTX 3060 | 12GB | Desktop workstations |
| `rtx4080.yaml` | RTX 4080 | 16GB | High-performance servers |

## Quick Start

### CPU (Default)

```bash
# The default config/pipeline.yaml already uses CPU settings
docker-compose up
```

### GPU

```bash
# 1. Copy the profile matching your GPU
cp config/profiles/rtx3060.yaml config/pipeline.yaml
# OR
cp config/profiles/rtx4080.yaml config/pipeline.yaml

# 2. Start with GPU support
docker-compose -f docker-compose.yaml -f config/profiles/docker-compose.gpu.yaml up
```

## GPU Support Status

> **Warning**: GPU configurations are currently **UNTESTED** - awaiting hardware delivery for validation.

The `device: cuda` settings in GPU profiles are commented out. Once GPU support is validated:

1. Uncomment the `device: cuda` lines in your profile
2. Ensure NVIDIA Container Toolkit is installed
3. Run with the GPU docker-compose override

## Performance Comparison (Estimated)

| Metric | CPU-Only | RTX 3060 | RTX 4080 |
|--------|----------|----------|----------|
| Embedding speed | 50-100 docs/min | 500-1000 docs/min | 1500-2000 docs/min |
| Query latency | 1-3s | 0.3-0.8s | 0.1-0.3s |
| Memory/VRAM | ~4GB RAM | ~4GB VRAM | ~8-10GB VRAM |
| Rerank candidates | 20 | 30 | 50 |

## Customization

Feel free to modify the profiles or create your own:

```yaml
# config/pipeline.yaml
embedding:
  batch_size: 16    # Reduce for low memory
  # device: cuda    # Enable GPU

reranking:
  enabled: false    # Disable for faster queries
  top_n: 10         # Fewer candidates = faster
```

## See Also

- [EXTENDING.md](../../docs/EXTENDING.md) - Adding custom implementations
- [PIPELINE.md](../../docs/PIPELINE.md) - Pipeline configuration guide
- [pipeline.yaml](../pipeline.yaml) - Active configuration
