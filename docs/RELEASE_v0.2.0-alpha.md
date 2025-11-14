## 🚀 Multi-Model Embedding Support

This release adds **configurable embedding models** with a focus on **Snowflake Arctic Embed 2.0**, providing significantly better retrieval quality for multi-domain knowledge bases.

## What's New

- ✨ **Arctic Embed 2.0-L** support (1024 dimensions, best quality)
- ✨ **Arctic Embed 2.0-M** support (768 dimensions, balanced)
- ⚙️ **Configurable model selection** via `.env` file
- 🎯 **Dynamic embedding dimensions** - automatically set based on model
- 📚 Support for **BGE** and **EmbeddingGemma** models from roadmap
- 🚀 **Docker optimization**: CPU-only PyTorch (~50% smaller images, 60% faster builds)
- 🔧 **Bug fixes**: PyTorch 2.5.1 compatibility with latest transformers

## Model Comparison

| Model | Dimensions | Quality | Speed | Use Case |
|-------|-----------|---------|-------|----------|
| all-MiniLM-L6-v2 (default) | 384 | Good | Fastest | Quick indexing, simple queries |
| Arctic Embed 2.0-M | 768 | Excellent | Moderate | Balanced quality/speed |
| Arctic Embed 2.0-L | 1024 | **Best** | Slower | Multi-domain KB, best retrieval |
| BGE-large-en-v1.5 | 1024 | Excellent | Moderate | Alternative high-quality option |

## Breaking Changes

⚠️ **Database Format Change**: Different embedding dimensions require re-indexing your knowledge base.

**If upgrading from v0.1.0**:
- Vector database must be rebuilt when switching models
- Your documents stay safe - only the vector embeddings change
- First-time model download - Arctic Embed 2.0-L is ~1.2GB
- Docker images now use CPU-only PyTorch (saves ~520MB)

📖 **[Migration Guide](https://github.com/KatanaQuant/rag-kb/blob/main/docs/MIGRATION_v0.1_to_v0.2.md)** - Step-by-step instructions with rollback procedures

## Quick Start (New Users)

```bash
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
git checkout v0.2.0-alpha

# Optional: Use Arctic Embed 2.0-L
cp .env.example .env
# Edit .env and uncomment: MODEL_NAME=Snowflake/snowflake-arctic-embed-l-v2.0

docker-compose up -d
```

## Upgrade Instructions (Existing Users)

```bash
cd /path/to/rag-kb
docker-compose down

# Backup your database
cp data/knowledge_base.db data/knowledge_base.db.backup

# Update to v0.2.0-alpha
git fetch origin
git checkout v0.2.0-alpha

# Optional: Configure new model
cp .env.example .env
# Edit .env and set MODEL_NAME

# Remove old database (incompatible dimensions)
rm data/knowledge_base.db

# Rebuild and reindex
docker-compose up --build -d
```

See the [Migration Guide](https://github.com/KatanaQuant/rag-kb/blob/main/docs/MIGRATION_v0.1_to_v0.2.md) for detailed instructions.

## Performance Notes

**Arctic Embed 2.0-L vs MiniLM-L6-v2**:
- **+45% better** on MTEB Retrieval benchmark
- **+40% better** on CLEF (multi-domain evaluation)
- **Indexing**: ~2-3x slower (still fast: 5-10 pages/sec for PDFs)
- **Query time**: Minimal difference (embeddings are pre-computed)
- **Storage**: ~2.7x larger vectors (1024 vs 384 dimensions)

**Docker Optimization**:
- **Image size**: ~1GB (was ~2GB)
- **Build time**: ~2-4 minutes (was ~5-10 minutes)
- **PyTorch download**: 185MB CPU-only (was 706MB CUDA)

## Bug Fixes

- Fixed PyTorch 2.1.2 incompatibility with transformers 4.57.1 by upgrading to PyTorch 2.5.1+cpu
- Fixed sentence-transformers compatibility with Arctic Embed 2.0 by upgrading to v5.1.2+
- Removed unnecessary CUDA dependencies for CPU-only operation

## Known Issues

- Manual MCP server startup required after VSCode restart
- No real-time indexing - requires container restart for new documents
- Model download on first startup adds 2-5 minutes (one-time, cached thereafter)

## Status

⚠️ **Early Alpha**: Breaking changes expected in future releases.

## Support

- **Issues**: https://github.com/KatanaQuant/rag-kb/issues
- **Migration Problems**: Open an issue with error logs and `.env` configuration
- **Email**: horoshi@katanaquant.com

---

**Full Changelog**: https://github.com/KatanaQuant/rag-kb/compare/v0.1.0-alpha...v0.2.0-alpha
