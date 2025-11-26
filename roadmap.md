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

### Anti-Malware / Security Validation ✅ (v1.2.0)
Prevents indexing of malicious or problematic files.

**Implemented:**
- ✅ File size validation (default: 500 MB max, 100 MB warn)
- ✅ Archive bomb detection (compression ratio, uncompressed size limits)
- ✅ Extension mismatch detection (executable renamed as document)
- ✅ Executable permission detection (files with +x bit, shebang)
- ✅ Integration with existing ExecutableCheckStrategy (ELF, PE, Mach-O)

**What it blocks:**
- Zip bombs (42.zip style attacks)
- File size bombs (> 500 MB files)
- Executables masquerading as documents
- Scripts with executable permissions
- Suspicious extension/content mismatches

## Planned Features

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
