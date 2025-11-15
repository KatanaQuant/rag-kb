# Docling PDF Integration Testing

This document describes the Docling PDF testing infrastructure for evaluating advanced PDF extraction.

## Overview

**Docling** is an advanced PDF processing library that provides better extraction quality for:
- Complex tables
- Multi-column layouts
- Headers and footers
- Mathematical formulas
- Scientific papers
- Embedded images and figures

## Testing Infrastructure

### Three Parallel Instances

| Instance | Port | Database | Knowledge Base | Purpose |
|----------|------|----------|----------------|---------|
| **Production** | 8000 | `data/` | `knowledge_base/` | PyMuPDF extraction (current) |
| **Test** | 8001 | `data_test/` | `knowledge_base_test/` | Model evaluation |
| **Docling** | 8002 | `data_docling/` | `knowledge_base_docling/` | Docling PDF testing |

### Directory Structure

```
RAG/
├── knowledge_base/           # Production KB (PyMuPDF)
├── knowledge_base_test/      # Test KB (model evaluation)
├── knowledge_base_docling/   # Docling KB (PDF quality testing)
├── data/                     # Production DB
├── data_test/               # Test DB
├── data_docling/            # Docling DB
├── docker-compose.yml        # Production instance
├── docker-compose.test.yml   # Test instance
├── docker-compose.docling.yml # Docling instance
└── docling-instance.sh       # Docling management script
```

## Quick Start

### 1. Start Docling Instance

```bash
./docling-instance.sh start
```

This will:
- Build Docker image with Docling support
- Start service on port 8002
- Create isolated database in `data_docling/`
- Watch `knowledge_base_docling/` directory

### 2. Add Test PDFs

```bash
cp test-pdfs/complex-tables.pdf knowledge_base_docling/
cp test-pdfs/multi-column.pdf knowledge_base_docling/
```

**Recommended test cases:**
- Scientific papers with equations
- Financial reports with tables
- Multi-column magazine layouts
- Documents with complex headers/footers

### 3. Reindex with Docling

```bash
./docling-instance.sh reindex
```

### 4. Compare Extraction Quality

**Side-by-side query comparison:**
```bash
./docling-instance.sh compare-query "what are the quarterly revenue figures"
```

This queries both production (PyMuPDF) and Docling instances, showing extraction differences.

**Stats comparison:**
```bash
./docling-instance.sh compare
```

Shows document/chunk counts across all three instances.

## Management Commands

### Start/Stop

```bash
./docling-instance.sh start    # Start Docling instance
./docling-instance.sh stop     # Stop Docling instance
./docling-instance.sh logs     # View logs (Ctrl+C to exit)
```

### Health & Status

```bash
./docling-instance.sh health   # Check health endpoint
./docling-instance.sh compare  # Compare all instances
```

### Querying

```bash
# Query Docling instance directly
./docling-instance.sh query "table extraction"

# Compare production vs Docling
./docling-instance.sh compare-query "table extraction"
```

### Data Management

```bash
./docling-instance.sh reindex  # Force reindex
./docling-instance.sh clean    # Remove DB, keep PDFs
./docling-instance.sh nuke     # Remove everything
```

## Testing Workflow

### Typical Evaluation Process

1. **Prepare test PDFs** with known complex structures
2. **Start both instances:**
   ```bash
   docker-compose up -d              # Production (PyMuPDF)
   ./docling-instance.sh start       # Docling
   ```

3. **Add same PDFs to both:**
   ```bash
   cp test.pdf knowledge_base/
   cp test.pdf knowledge_base_docling/
   ```

4. **Reindex both:**
   ```bash
   curl -X POST http://localhost:8000/index -d '{"force_reindex": true}'
   ./docling-instance.sh reindex
   ```

5. **Compare results:**
   ```bash
   ./docling-instance.sh compare-query "specific content from PDF"
   ```

6. **Evaluate quality:**
   - Are tables extracted correctly?
   - Are formulas readable?
   - Is multi-column layout preserved?
   - Are headers/footers handled properly?

## Configuration

### Environment Variables

Set in `docker-compose.docling.yml`:

```yaml
environment:
  - USE_DOCLING=true           # Enable Docling extraction
  - MODEL_NAME=snowflake/arctic-embed-l-v2.0
  - WATCH_ENABLED=false        # Disable auto-watch for testing
```

### Enabling Docling in Code

The `USE_DOCLING` environment variable should trigger Docling-specific processing in [api/ingestion.py](../api/ingestion.py).

## Expected Differences

### PyMuPDF (Production)
**Pros:**
- Fast extraction (~10-20 pages/sec)
- Lightweight
- Good for simple PDFs

**Cons:**
- Tables often mangled
- Multi-column layouts merged incorrectly
- Formulas extracted as symbols
- Headers/footers mixed with content

### Docling (Test)
**Pros:**
- Better table extraction
- Layout-aware processing
- Formula preservation
- Structured output

**Cons:**
- Slower processing
- More dependencies
- Higher resource usage

## Metrics to Compare

1. **Extraction accuracy** - Do queries return correct content?
2. **Table handling** - Are tables readable and structured?
3. **Layout preservation** - Is document structure maintained?
4. **Processing speed** - Chunks/second throughput
5. **Resource usage** - Memory and CPU consumption

## Rollout Decision

After testing, decide:

- **Keep PyMuPDF** if Docling shows minimal improvement
- **Switch to Docling** if extraction quality justifies overhead
- **Hybrid approach** - Docling for complex PDFs, PyMuPDF for simple ones
- **Optional feature** - Let users choose extraction method

## Troubleshooting

### Docling instance won't start

```bash
# Check logs
./docling-instance.sh logs

# Verify port availability
lsof -i :8002

# Rebuild from scratch
./docling-instance.sh stop
docker-compose -f docker-compose.docling.yml build --no-cache
./docling-instance.sh start
```

### Extraction still looks poor

- Try different Docling processing options
- Check PDF is not scanned/image-based (use OCR separately)
- Verify USE_DOCLING=true in environment

### High memory usage

- Reduce batch size: `BATCH_SIZE=2`
- Process fewer documents at once
- Lower resource limits in docker-compose

## Next Steps

After evaluating Docling:

1. **Document findings** - Add results to this file
2. **Update implementation** - Integrate Docling if beneficial
3. **Clean up test infrastructure** - Remove if not needed
4. **Update README** - Document Docling as optional feature

---

**Status**: Infrastructure ready, awaiting PDF testing
**Last Updated**: 2025-11-15
