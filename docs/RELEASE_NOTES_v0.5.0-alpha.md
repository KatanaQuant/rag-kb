# Release Notes - v0.5.0-alpha

**Release Date**: 2025-11-15
**Status**: Alpha Release Candidate
**Previous Stable**: v0.4.0-alpha

---

## Overview

This release establishes Docling as the default PDF extraction engine for RAG-KB, replacing PyPDF. Docling provides advanced table extraction, layout preservation, and document structure recognition, significantly improving chunk quality for technical documents.

**Note**: This is a CPU-focused build. Large knowledge bases may require significant processing time (see Performance section below).

---

## Major Features

### Docling PDF Integration (Default)

**What's New:**
- Advanced PDF extraction with table structure detection
- Layout analysis and multi-column preservation
- Clean mathematical formula extraction
- Document hierarchy preservation (headers, lists, code blocks)
- Markdown output with structure intact
- PyPDF fallback for compatibility

**Configuration:**
```bash
USE_DOCLING=true  # Default
DOCLING_ARTIFACTS_PATH=/path/to/cache
TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
```

### Pipeline Visibility & Logging

**What's New:**
- Stage-by-stage completion logging
- Extraction, chunking, embedding, and storage progress tracking
- Detailed character and chunk count reporting
- Processing time visibility for performance analysis

**Example Output:**
```
Extraction complete: book.pdf - 490,275 chars extracted
Chunking complete: book.pdf - 739 chunks created
Embedding complete: book.pdf - 739 chunks embedded
Indexed book.pdf: 739 chunks stored
```

### CPU Performance Benchmarking

**Benchmark Results** (AMD Ryzen, 6 cores, Snowflake Arctic Embed L):
- Test document: 2.8MB PDF (Practical OOD in Ruby)
- Total processing time: 37 minutes
- Extraction: 15 min (Docling + Tesseract OCR)
- Chunking: <1 min (739 chunks created)
- Embedding: 22 min (~34 chunks/minute)
- Storage: Instant (741 total chunks)

**Scaling Estimates:**
| Knowledge Base Size | Est. Processing Time |
|---------------------|---------------------|
| 10 PDFs (28MB) | 6-7 hours |
| 50 PDFs (140MB) | 30-35 hours |
| 100 PDFs (280MB) | 60-70 hours |
| 500 PDFs (1.4GB) | 12-15 days |

**Note**: Estimates assume similar PDF complexity. Technical books with tables/formulas may take longer.

---

## Performance & Optimization

### CPU vs GPU Comparison

**CPU Performance** (Current):
- 2.8MB PDF: 37 minutes
- 100 PDFs: ~62 hours

**GPU Performance** (Estimated with RTX 3090):
- 2.8MB PDF: 30-60 seconds (60x faster)
- 100 PDFs: ~1 hour
- Speedup: 60-150x depending on model

### Performance Recommendations

1. **English-only content**: Switch to `sentence-transformers/static-retrieval-mrl-en-v1` for 100-400x speedup with minimal quality trade-off
2. **Large knowledge bases**: Consider GPU build ($750-$2,500 hardware investment) or overnight processing budget
3. **OCR-heavy PDFs**: Consider disabling OCR if documents have text layers

### Resource Configuration

```yaml
deploy:
  resources:
    limits:
      cpus: '6.0'
      memory: 6G
    reservations:
      cpus: '0.5'
      memory: 512M
```

---

## Testing Infrastructure

### Docling Test Instance

**Configuration:**
- Port: 8002 (isolated from production on 8000)
- Database: `data_docling/rag.db`
- Knowledge Base: `knowledge_base_docling/`
- Docker Compose: `docker-compose.docling.yml`

**Model Caching:**
- DeepSearch GLM: `.cache/deepsearch_glm`
- Docling models: `.cache/docling`
- HuggingFace models: `.cache/huggingface`
- EasyOCR models: `.cache/easyocr`

---

## Documentation

### New Documentation

- `docs/docling-cpu-benchmark.md` - Complete CPU processing benchmark
- `docs/pdf-extraction-alternatives.md` - Roadmap for PyMuPDF4LLM and Marker-PDF
- Updated README.md - CPU-focused build warnings and performance guidance

### Documentation Updates

- README clarified as CPU-focused build
- Added processing time estimates (Small/Medium/Large KB)
- Added performance recommendations section
- Clarified Claude Code integration requirements
- Updated model recommendations

---

## Technical Changes

### API Changes

**New Environment Variables:**
- `USE_DOCLING` - Enable/disable Docling (default: true)
- `DOCLING_ARTIFACTS_PATH` - Docling model cache path
- `TESSDATA_PREFIX` - Tesseract OCR data path

**Modified Files:**
- `api/ingestion.py` - Added DoclingExtractor, pipeline logging
- `api/main.py` - Added embedding and storage completion logging
- `api/Dockerfile` - Added Tesseract OCR, DeepSearch GLM permissions
- `api/requirements.txt` - Added `docling[easyocr]==1.20.0`

### Docker Configuration

**New Compose File:**
- `docker-compose.docling.yml` - Isolated Docling test instance

**Modified Compose:**
- `docker-compose.yml` - Updated resource limits and cache volumes

---

## Migration Guide

### From v0.4.0-alpha (PyPDF) to v0.5.0-alpha (Docling)

**Step 1: Backup existing data**
```bash
cp -r data/ data_backup/
cp -r knowledge_base/ knowledge_base_backup/
```

**Step 2: Pull and rebuild**
```bash
git pull origin main
docker-compose build
```

**Step 3: Start service**
```bash
docker-compose up -d
```

**Step 4: Monitor processing**
```bash
docker logs rag-api -f
```

**Note**: First startup will download ~3GB of models (Docling, Arctic Embed). This is a one-time download.

### Reverting to PyPDF

If you need to revert to PyPDF extraction:

```bash
# In .env or docker-compose.yml
USE_DOCLING=false
```

Restart the service:
```bash
docker-compose restart rag-api
```

---

## Known Issues

### Non-Critical

1. **Manual MCP Server Startup** (P3 - Nuisance)
   - Must manually activate via "MCP: List Servers" after VSCode restart
   - Workaround: Run command after VSCode opens
   - Fix: Investigate VSCode MCP auto-discovery config

2. **Long Processing Times** (P2 - Design Choice)
   - CPU-only processing is inherently slow for large documents
   - Mitigation: Use test instance for experimentation, batch process overnight
   - Future: GPU build option in development

---

## Breaking Changes

None. This release is backward compatible with v0.4.0-alpha.

---

## Future Work (v0.6.0-alpha)

1. **Intelligent Chunking**: Explore semantic chunking vs current fixed-size approach
2. **PyMuPDF4LLM Integration**: 10-100x faster alternative for tables (no OCR)
3. **Marker-PDF Support**: For OCR-heavy scanned documents
4. **Resumable Processing**: Checkpoint-based processing for long documents
5. **GPU Support**: Hardware acceleration for embedding generation

---

## Acknowledgments

This release focuses on improving PDF extraction quality while maintaining the CPU-only build philosophy. Feedback and testing from the community helped identify the need for better pipeline visibility and performance documentation.

---

## Verification

To verify this release is working correctly:

1. Check health endpoint:
```bash
curl http://localhost:8000/health
```

2. Test query:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your query", "top_k": 5}'
```

3. Check logs for Docling initialization:
```bash
docker logs rag-api 2>&1 | grep -i docling
```

Expected: Should see "Docling PDF extraction initialized"

---

**Download**: [GitHub Release v0.5.0-alpha](https://github.com/KatanaQuant/rag-kb/releases/tag/v0.5.0-alpha)
**Stable Version**: [v0.4.0-alpha](https://github.com/KatanaQuant/rag-kb/releases/tag/v0.4.0-alpha)
