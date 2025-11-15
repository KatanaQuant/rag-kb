# Release v0.5.0-alpha: Docling PDF Integration

**Release Date**: 2025-11-15
**Type**: Feature Release
**Status**: Alpha (Pre-release)

---

## What's New

### Docling PDF Integration (Now Default)

Advanced PDF extraction using [Docling](https://github.com/DS4SD/docling) library for significantly better quality:

- **Tables**: Structured, readable data vs mangled text
- **Multi-column layouts**: Proper text flow preserved
- **Mathematical formulas**: Clean extraction
- **Headers/footers**: Properly handled
- **Complex documents**: Scientific papers, technical books, financial reports

**Configuration**:
- Default: `USE_DOCLING=true` (advanced extraction)
- Fallback: `USE_DOCLING=false` (PyPDF for speed)

### Testing & Migration Infrastructure

- **Side-by-side testing**: Compare PyPDF vs Docling before switching
- **Zero-downtime migration**: Run both instances simultaneously
- **Management scripts**: `./docling-instance.sh` for easy control
- **Isolated testing**: Separate port (8002), database, knowledge base

### Documentation

- **[MIGRATION_TO_DOCLING.md](MIGRATION_TO_DOCLING.md)**: Complete migration guide with rollback procedures
- **[docs/DOCLING_TESTING.md](DOCLING_TESTING.md)**: Testing infrastructure documentation
- Updated README with Docling features and usage

---

## Installation

### New Installation

```bash
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
git checkout v0.5.0-alpha

# Start with Docling (default)
docker-compose up -d

# Or disable Docling for faster processing
echo "USE_DOCLING=false" > .env
docker-compose up -d
```

### Upgrading from v0.4.0-alpha

**Option A: Zero-Downtime Migration** (Recommended)

```bash
cd rag-kb
git pull origin main
git checkout v0.5.0-alpha

# Test Docling on port 8002 while production runs on 8000
./docling-instance.sh start

# Copy knowledge base for comparison
cp -r knowledge_base/* knowledge_base_docling/
./docling-instance.sh reindex

# Compare quality
./docling-instance.sh compare-query "your test query"

# Switch when ready (see MIGRATION_TO_DOCLING.md)
```

**Option B: Direct Upgrade**

```bash
cd rag-kb
git pull origin main
git checkout v0.5.0-alpha

# Backup current database
cp data/rag.db data/rag.db.v0.4.0-backup

# Rebuild and reindex (Docling is default)
docker-compose down
docker-compose up --build -d

# Monitor indexing (slower than PyPDF but higher quality)
docker-compose logs -f rag-api
```

---

## Breaking Changes

**None**. Fully backward compatible with v0.4.0-alpha.

- Existing databases continue to work
- PyPDF fallback available via `USE_DOCLING=false`
- No configuration changes required

---

## Performance Considerations

### Processing Speed
- **Docling**: ~2-5 pages/sec (higher quality, slower)
- **PyPDF**: ~10-20 pages/sec (faster, lower quality)

### Memory Usage
- **Docling**: ~1.5-2GB (includes detection models)
- **PyPDF**: ~500MB-1GB

### Docker Image
- **Docling**: ~1.5GB (+500MB dependencies)
- **PyPDF**: ~1GB

### First Run
- Docling downloads detection models (~500MB) on first startup
- Models are cached for subsequent runs
- First-run time: +5-10 minutes

---

## Migration Guide

See **[MIGRATION_TO_DOCLING.md](MIGRATION_TO_DOCLING.md)** for:
- Step-by-step migration instructions
- Zero-downtime deployment strategy
- Rollback procedures
- Performance expectations
- FAQ

---

## Rollback to v0.4.0-alpha

If you encounter issues:

```bash
# Stop current instance
docker-compose down

# Restore v0.4.0 database (if backed up)
cp data/rag.db.v0.4.0-backup data/rag.db

# Revert to v0.4.0
git checkout v0.4.0-alpha

# Restart with PyPDF
docker-compose up -d
```

---

## Full Changelog

### Features

- Docling PDF integration (default extraction method)
- Isolated testing infrastructure (port 8002, separate KB/DB)
- Management script for Docling test instance
- Zero-downtime migration workflow
- Side-by-side quality comparison tools

### Enhancements

- Comprehensive migration documentation
- Docling marked as implemented in roadmap
- Configurable PDF extraction method (USE_DOCLING env var)
- Database filename references corrected (rag.db)

### Documentation

- Added MIGRATION_TO_DOCLING.md
- Added docs/DOCLING_TESTING.md
- Updated README with Docling features
- Updated roadmap to reflect completion

### Infrastructure

- docker-compose.docling.yml for test instance
- docling-instance.sh management script
- knowledge_base_docling/ testing directory
- data_docling/ isolated database

---

## Known Issues

### First Run Download Time

Docling downloads detection models (~500MB) on first startup. This is normal and only happens once.

**Workaround**: Use PyPDF for initial indexing, then switch to Docling:
```bash
echo "USE_DOCLING=false" > .env
docker-compose up -d
# After indexing completes, enable Docling and reindex
```

### Memory Usage

Docling requires ~1.5-2GB RAM. On resource-constrained systems, consider:
- Using PyPDF instead (`USE_DOCLING=false`)
- Processing fewer documents at once
- Increasing Docker memory limits

---

## Upgrading

**From v0.4.0-alpha**: Seamless upgrade, see instructions above
**From v0.3.0-alpha or earlier**: Upgrade to v0.4.0-alpha first, then v0.5.0-alpha

---

## Testing

Run comprehensive test suite:

```bash
# Unit tests
cd api && python -m pytest tests/ -v

# Integration test with Docling
./docling-instance.sh start
./docling-instance.sh query "test query"
./docling-instance.sh health
./docling-instance.sh stop
```

---

## Contributors

**Project maintained by**: KatanaQuant

Special thanks to the Docling team for the excellent PDF parsing library.

---

## Support

- **Documentation**: [README.md](https://github.com/KatanaQuant/rag-kb/blob/main/README.md)
- **Migration Guide**: [MIGRATION_TO_DOCLING.md](https://github.com/KatanaQuant/rag-kb/blob/main/MIGRATION_TO_DOCLING.md)
- **Issues**: [GitHub Issues](https://github.com/KatanaQuant/rag-kb/issues)
- **Email**: horoshi@katanaquant.com

---

## What's Next

See the [Roadmap](https://github.com/KatanaQuant/rag-kb#roadmap) for upcoming features:

- OCR support for scanned PDFs
- GPU acceleration for embeddings
- Additional embedding models
- Performance optimization for Docling

---

**Previous Release**: [v0.4.0-alpha](https://github.com/KatanaQuant/rag-kb/releases/tag/v0.4.0-alpha)
**Repository**: [https://github.com/KatanaQuant/rag-kb](https://github.com/KatanaQuant/rag-kb)
