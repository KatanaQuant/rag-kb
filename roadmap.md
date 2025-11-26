# Roadmap

## Completed Features

### Document Completeness Verification ✅ (v1.1.0)
Validates that indexed documents are complete and intact.

**Implemented:**
- ✅ Chunk count tracking and verification
- ✅ Processing status validation
- ✅ Database chunk existence checks (orphan detection)
- ✅ Unified completeness API: `GET /documents/completeness`
- ✅ Maintenance CLI (`manage.py`)
- ✅ Migration script for historical data
- ✅ PDF integrity validation (5-check pre-flight validation)

**Remaining:**
- Performance optimization (batch queries instead of N+1)

## Planned Features

### Anti-Malware / Security Validation (NEXT)
Prevent indexing of malicious or problematic files.

**Needed:**
- Executable detection (ELF, PE, Mach-O headers)
- Script detection (shell, Python, etc with shebang or exec permissions)
- Archive bomb detection (nested archives, compression ratios)
- File size limits and validation
- Suspicious extension mismatches

### Performance Optimization
The completeness API is slow (~3 minutes for 1300 documents).

**Needed:**
- Batch database queries (currently N+1 pattern)
- Optional pagination for large knowledge bases
- Caching layer for repeated checks

### Content Quality Strategies (Future)
Additional extraction quality checks:

| Strategy | Purpose |
|----------|---------|
| BlankPageStrategy | Detect near-empty pages |
| CharDistributionStrategy | Flag statistical outliers |
| OCRConfidenceStrategy | Track OCR quality scores |

## Known Issues

### Completeness Check Performance
The `/documents/completeness` endpoint queries each document individually. For large knowledge bases (1000+ docs), this takes several minutes.

**Workaround:** Run health checks during off-peak hours or use `manage.py health` with extended timeout.
