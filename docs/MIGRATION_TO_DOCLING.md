# Migration to Docling PDF Extraction

**Purpose**: Migrate production instance from PyPDF to Docling for improved PDF extraction quality (tables, layouts, formulas).

**Estimated Time**: 30-60 minutes (depending on PDF count)
**Difficulty**: Medium
**Downtime**: Minimal (zero-downtime approach available)

---

## Overview

Docling provides significantly better PDF extraction for:
- Complex tables → Structured, readable data
- Multi-column layouts → Proper text flow preserved
- Mathematical formulas → Clean extraction
- Headers/footers → Properly handled

**Trade-off**: Slower processing (~2-5x vs PyPDF), larger Docker image (~500MB more dependencies)

---

## Migration Approaches

### Approach 1: Zero-Downtime (Recommended)

Run both instances side-by-side, then switch over.

**Step 1: Start Docling Instance**

```bash
# Docling instance will run on port 8002
./docling-instance.sh start

# Wait for model download (first run only, ~5-10 min)
docker logs rag-api-docling -f

# Verify it's healthy
./docling-instance.sh health
```

**Step 2: Copy Knowledge Base**

```bash
# Copy all files to Docling KB
cp -r knowledge_base/* knowledge_base_docling/

# Trigger reindex
./docling-instance.sh reindex

# Monitor progress (Docling is slower, be patient)
docker logs rag-api-docling -f
```

**Step 3: Compare Quality**

```bash
# Test same query on both instances
./docling-instance.sh compare-query "system design load balancing"

# Check if tables/formulas are better extracted
# Review specific PDFs that had extraction issues
```

**Step 4: Switch Production**

Once satisfied with Docling quality:

```bash
# Option A: Make Docling the new production (port 8000)
docker-compose down  # Stop old PyPDF instance

# Update docker-compose.yml to enable Docling:
echo "USE_DOCLING=true" >> .env

# Backup old database
cp data/rag.db data/rag.db.pypdf-backup-$(date +%Y%m%d)

# Copy Docling database to production
cp data_docling/rag.db data/rag.db

# Start production with Docling
docker-compose up --build -d

# Option B: Keep Docling on port 8002
# Just update MCP config to point to :8002 instead of :8000
```

**Step 5: Update MCP Configuration** (if needed)

```bash
# Edit MCP config
vim ~/.config/claude-code/mcp.json

# Change RAG_API_URL from :8000 to :8002
# Or keep at :8000 if you chose Option A above
```

**Step 6: Verify & Clean Up**

```bash
# Test MCP integration
# In Claude Code: "Query knowledge base for [test topic]"

# If all works, clean up old instance (after a few days)
rm -rf data_docling knowledge_base_docling
./docling-instance.sh nuke
```

---

### Approach 2: Direct Migration (Simpler, Has Downtime)

Replace production instance directly with Docling.

**Step 1: Backup**

```bash
# Backup current database and config
cp data/rag.db data/rag.db.pypdf-backup-$(date +%Y%m%d)
cp .env .env.backup
```

**Step 2: Enable Docling**

```bash
# Add USE_DOCLING=true to .env
echo "USE_DOCLING=true" >> .env

# Stop and remove old database
docker-compose down
rm data/rag.db
```

**Step 3: Rebuild & Reindex**

```bash
# Rebuild with Docling support
docker-compose up --build -d

# Monitor indexing (will be slower than PyPDF)
docker-compose logs -f rag-api
```

**Step 4: Verify**

```bash
# Check health
curl http://localhost:8000/health | jq

# Test queries
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query with tables", "top_k": 3}' | jq
```

---

## Rollback Instructions

### If Using Zero-Downtime Approach

```bash
# Simply switch MCP back to :8000 (PyPDF instance)
# Edit ~/.config/claude-code/mcp.json

# Or restart PyPDF production:
docker-compose up -d

# Stop Docling test instance:
./docling-instance.sh stop
```

### If Using Direct Migration

```bash
# Stop Docling instance
docker-compose down

# Restore PyPDF database
cp data/rag.db.pypdf-backup-YYYYMMDD data/rag.db

# Disable Docling
sed -i '/USE_DOCLING=true/d' .env
# Or manually remove USE_DOCLING from .env

# Restart with PyPDF
docker-compose up -d
```

---

## Performance Expectations

### Processing Speed
- **PyPDF**: ~10-20 pages/sec
- **Docling**: ~2-5 pages/sec (slower but higher quality)

### Memory Usage
- **PyPDF**: ~500MB-1GB
- **Docling**: ~1.5-2GB (detection models)

### Docker Image Size
- **PyPDF**: ~1GB
- **Docling**: ~1.5GB (+500MB dependencies)

### First Run
- Docling downloads detection models (~500MB) on first startup
- This is cached for future runs
- Total first-run time: +5-10 minutes

---

## FAQ

**Q: Will Docling change my existing data?**
A: No. It only affects how NEW PDFs are extracted. Existing chunks remain unchanged unless you force reindex.

**Q: Can I run both PyPDF and Docling permanently?**
A: Yes! Keep production on PyPDF (port 8000) and Docling test instance (port 8002). Switch between them as needed.

**Q: Does Docling work with all PDFs?**
A: Docling works best with text-based PDFs. Scanned/image PDFs still need OCR preprocessing (not included).

**Q: How do I test if Docling is actually better for my docs?**
A: Use the zero-downtime approach and run `./docling-instance.sh compare-query` on representative queries from your domain.

**Q: Can I switch back to PyPDF later?**
A: Yes, anytime. Just set `USE_DOCLING=false` in `.env` and reindex.

---

## Support

- Docling Documentation: [docs/DOCLING_TESTING.md](docs/DOCLING_TESTING.md)
- Issues: https://github.com/KatanaQuant/rag-kb/issues
- Email: horoshi@katanaquant.com
