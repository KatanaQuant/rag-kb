# Docling CPU Processing Benchmark

## Test Configuration

**Hardware**: AMD Ryzen CPU (6 cores allocated)
**Model**: Snowflake/arctic-embed-l-v2.0 (1024 dimensions)
**Batch Size**: 5 chunks per batch
**Memory Limit**: 6GB

## Test Document

**File**: Practical Object-Oriented Design in Ruby by Sandi Metz
**Size**: 2.8MB PDF
**Content**: 490,275 characters extracted

## Processing Timeline

| Stage | Duration | CPU Usage | Details |
|-------|----------|-----------|---------|
| **Extraction** (Docling + EasyOCR) | ~15 min | 300-360% | 490,275 chars extracted |
| **Chunking** | <1 min | - | 739 chunks created |
| **Embedding** | ~22 min | 290-310% | 739 chunks @ ~34 chunks/min |
| **Storage** | Instant | - | 741 total chunks (739 PDF + 2 README) |
| **TOTAL** | **37 minutes** | - | End-to-end processing |

## Performance Analysis

**Extraction Phase** (15 minutes):
- Docling PDF parsing with PyPdfium backend
- Table structure detection enabled
- OCR enabled via Tesseract (not EasyOCR as initially configured)
- ~180 KB/min throughput

**Embedding Phase** (22 minutes):
- Snowflake Arctic Embed L model (1024-dim)
- Batch processing: 5 chunks per batch
- ~34 chunks/minute processing rate
- ~148 total batches (739 chunks ÷ 5)

## Scaling Estimates

Based on 37 minutes per 2.8MB PDF:

| Knowledge Base Size | Est. Processing Time |
|---------------------|---------------------|
| 10 PDFs (28MB) | 6-7 hours |
| 50 PDFs (140MB) | 30-35 hours |
| 100 PDFs (280MB) | 60-70 hours |
| 500 PDFs (1.4GB) | 300-350 hours (12-15 days) |

**Note**: Estimates assume similar PDF complexity. Technical books with tables/formulas will take longer.

## CPU vs GPU Comparison

**CPU Performance** (Current):
- 2.8MB PDF: 37 minutes
- 100 PDFs: ~62 hours

**GPU Performance** (Estimated with RTX 3090):
- 2.8MB PDF: 30-60 seconds (60x faster)
- 100 PDFs: ~1 hour
- Speedup: 60-150x depending on model

## Recommendations

1. **English-only content**: Switch to `sentence-transformers/static-retrieval-mrl-en-v1` for 100-400x speedup
2. **Large knowledge bases**: Consider GPU build ($750-$2,500 hardware investment)
3. **Production use**: Budget overnight processing for medium KBs (50-100 docs)
4. **OCR-heavy PDFs**: Consider disabling OCR if documents have text layers

## Test Date

2025-11-15
