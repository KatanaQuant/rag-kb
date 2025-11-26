# Internal Planning

## Document Completeness Verification

### Problem
No way to verify documents are fully processed - missing pages in PDFs, truncated extractions, or embedding failures go undetected.

### Current State
**Existing mechanisms:**
- `orphan_detector.py` - detects files marked completed but missing embeddings
- `helpers.py` - SHA256 file hashing for change detection
- `progress.py` - tracks status per file (in_progress/completed/failed)
- `file_type_validator.py` - magic bytes, extension, existence checks
- `database.py` routes - duplicate detection/cleanup

**Gaps:**
- `processing_progress.total_chunks` exists but never populated (always 0)
- No PDF page count comparison (claimed vs extracted)
- No embedding count validation (chunks vs vectors)
- No unified completeness status endpoint
- Failed documents queryable but no dashboard

### Implementation Plan

#### Phase 1: Chunk Count Tracking
- Populate `total_chunks` in `processing_progress` during extraction
- Add `chunks_embedded` counter
- Verify: `chunks_processed == total_chunks == chunks_embedded`

**Files to modify:**
- `api/ingestion/progress.py` - update tracking methods
- `api/ingestion/processing.py` - populate counts during extraction
- `api/ingestion/embedding_service.py` - track embedded count

#### Phase 2: Content Quality Validation (Replaces Simple Page Count)

**Why not simple page count?**
- PDF `/Count` metadata often mismatches extractable pages
- Cover pages, TOC use different numbering (roman vs arabic)
- Scanned PDFs with OCR overlays have metadata inconsistencies
- Research: [Enterprise RAG fails 40% due to doc quality](https://www.banandre.com/blog/enterprise-rag-implementation-challenges-revealed)

**Content-based detection strategies:**

| Strategy | Detection Method | Threshold |
|----------|-----------------|-----------|
| `BlankPageStrategy` | `len(page_text.strip()) < 50` | Flag pages with <50 chars |
| `EmptyContentStrategy` | `page.get_contents() == []` | PyMuPDF empty page check |
| `OCRConfidenceStrategy` | Tesseract confidence score | Warn if avg <30% |
| `CharDistributionStrategy` | Chars per page vs avg | Flag outliers (>2 std dev) |
| `ImageExtractionStrategy` | `page.get_images()` failures | Track extraction success % |
| `TOCValidationStrategy` | Bookmark refs → actual pages | Flag dangling refs |

**Implementation:**
```python
class ContentQualityAnalyzer:
    """Analyzes extraction quality without relying on page count metadata"""

    def analyze(self, extracted_pages: List[Tuple[str, int]]) -> QualityReport:
        strategies = [
            BlankPageStrategy(min_chars=50),
            CharDistributionStrategy(std_dev_threshold=2.0),
            # OCRConfidenceStrategy only if OCR was used
        ]
        return self._run_strategies(extracted_pages, strategies)
```

**Files to modify:**
- `api/ingestion/extractors/docling_extractor.py` - capture quality metrics
- `api/ingestion/completeness_strategies.py` - add content strategies

**Sources:**
- [PyMuPDF OCR docs](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html)
- [OCR quality limits RAG](https://www.mixedbread.com/blog/the-hidden-ceiling)
- [Detecting broken PDF pages](https://stackoverflow.com/questions/68329240/how-to-identify-likely-broken-pdf-pages-before-extracting-its-text)

#### Phase 3: Completeness API
- New endpoint: `GET /documents/completeness-report`
- Returns: total docs, complete, incomplete, failed, missing embeddings
- Per-document breakdown available via query param

**Files to create:**
- `api/routes/completeness.py`
- `api/api_services/completeness_service.py`

#### Phase 4: Embedding Validation
- Count vectors in `vec_chunks` per document
- Compare against chunk count in `documents`
- Detect partial embedding failures

**Files to modify:**
- `api/api_services/completeness_service.py`

### Database Schema Changes
```sql
-- Add to processing_progress (already exists, just needs population)
total_chunks INTEGER DEFAULT 0
chunks_processed INTEGER DEFAULT 0

-- Consider adding
expected_pages INTEGER  -- for PDFs
extracted_pages INTEGER
embedding_count INTEGER
```

### API Response Shape
```json
{
  "total_documents": 150,
  "complete": 145,
  "incomplete": 3,
  "failed": 2,
  "issues": [
    {
      "file_path": "/path/to/doc.pdf",
      "issue": "page_mismatch",
      "expected": 100,
      "actual": 95
    }
  ]
}
```
