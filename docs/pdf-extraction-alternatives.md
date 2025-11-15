# PDF Extraction Alternatives Roadmap

## Current Implementation: Docling (CPU-optimized)

**Status**: Active (v0.6.0-alpha)
**Configuration**: OCR disabled, table extraction enabled, PyPdfium backend
**Performance**: 0.3-3 sec/page (CPU-only)
**Capabilities**:
- Markdown output with structure preservation
- Table extraction and formatting
- Layout analysis
- Document hierarchy (headers, lists, code blocks)

**Limitations**:
- No OCR for scanned PDFs
- Requires text layer in PDF
- CPU-only (no GPU acceleration on AMD Vega)

---

## Alternative 1: PyMuPDF4LLM

**Status**: Backburner (ready for implementation if Docling insufficient)
**Performance**: <1 sec/page (10-100x faster than Docling)
**Installation**: `pip install pymupdf4llm`

### Capabilities Match Docling
- ✓ Markdown output
- ✓ Table detection and formatting
- ✓ Document structure (headers, lists, code blocks)
- ✓ Reading order preservation
- ✓ Image detection
- ✗ No OCR
- ✗ Heuristic-based layout (not ML)

### Integration Plan
1. Add PyMuPDF4LLM to requirements.txt
2. Create `PyMuPDFExtractor` class in ingestion.py
3. Add `USE_PYMUPDF` environment variable
4. Implement same interface as DoclingExtractor
5. Test on production PDFs for quality comparison

### Expected Performance
- 500-page PDF: 60-500 seconds (vs Docling 150-1500 sec)
- Memory usage: Lower than Docling
- Chunk quality: Comparable for text-heavy documents

---

## Alternative 2: Marker-PDF

**Status**: Backburner (for OCR use case)
**Performance**: 16+ sec/page (CPU-only)
**Installation**: `pip install marker-pdf`

### Capabilities Beyond Docling
- ✓ Markdown output
- ✓ Table extraction
- ✓ **OCR support** (scanned PDFs)
- ✓ Equation detection
- ✓ Code block formatting
- ✓ GPU/CPU/MPS support

### When to Consider
- User uploads scanned PDFs requiring OCR
- Need equation/formula preservation
- Future GPU hardware upgrade (10x speedup)

### Integration Plan
1. Add marker-pdf to optional-requirements.txt
2. Create `MarkerExtractor` class with OCR toggle
3. Add `USE_MARKER` and `MARKER_OCR_ENGINE` variables
4. Implement async processing for long documents
5. Add progress tracking for user feedback

### Performance Expectations
- 500-page PDF: 2-4 hours (CPU-only)
- With GPU (future): 10-30 minutes
- Memory: 2-4GB during processing

---

## Alternative 3: PyPDF (Current Fallback)

**Status**: Active (fallback when Docling fails)
**Performance**: 30-150 sec for 500-page PDF
**Capabilities**:
- Plain text extraction only
- No table detection
- No structure preservation
- No markdown output

### Use Case
- Emergency fallback
- Ultra-fast basic text needs
- Documents with no tables/structure

---

## Decision Matrix

| Requirement | Docling | PyMuPDF4LLM | Marker-PDF | PyPDF |
|-------------|---------|-------------|------------|-------|
| Speed (500pg) | 2-25 min | 1-8 min | 2-4 hrs | 0.5-2 min |
| Tables | ✓ | ✓ | ✓ | ✗ |
| Structure | ✓ | ✓ | ✓ | ✗ |
| Markdown | ✓ | ✓ | ✓ | ✗ |
| OCR | ✗ | ✗ | ✓ | ✗ |
| CPU stable | ✓* | ✓ | ✓ | ✓ |
| Memory | 1-2GB | <500MB | 2-4GB | <100MB |

*After disabling OCR

---

## Migration Path

### Phase 1: Validate Docling (Current)
- Test fixed Docling on production PDFs
- Measure processing times
- Assess chunk quality vs PyPDF baseline

### Phase 2: Implement PyMuPDF4LLM (If needed)
- Add as alternative backend
- A/B test chunk quality
- Benchmark speed improvement
- Make configurable via environment variable

### Phase 3: Add Marker-PDF (If OCR needed)
- Implement for OCR use case
- Add document type detection (scanned vs native)
- Auto-select appropriate extractor
- Add user override option

---

## Implementation Notes

All alternatives must:
1. Return markdown text (not plain text chunks)
2. Preserve document structure
3. Handle tables and lists correctly
4. Support the same interface as current extractors
5. Allow chunking at the ingestion layer (not extraction layer)
6. Provide same metadata (source, page, file_path)

**Critical**: Do NOT implement "1000 char chunking" at extraction level. All extractors return full document markdown, chunking happens in `TextChunker` class.
