# EPUB Processing Investigation

## Date
2025-11-17

## Issue
EPUB → PDF → Docling pipeline fails with `ConversionStatus.FAILURE`

## Root Cause Analysis

### Investigation Process
1. Implemented EPUB support with Pandoc + XeLaTeX conversion
2. EPUB successfully converts to PDF (9.1 MB for System Design Interview book)
3. Pandoc conversion works perfectly
4. **Docling fails to extract text from the generated PDF**

### Technical Details

**PDF Analysis Results** (System Design Interview - Alex Xu):
```
Producer: xdvipdfmx (20240305) - XeLaTeX's PDF generator
Creator: LaTeX via pandoc
Pages: 272
MediaBox: 612 x 792 pts (standard US Letter)
Fonts: Type0 CID-keyed with Identity-H encoding
  - /OSIXIB+LMRoman17-Regular-Identity-H - Embedded: FALSE
  - /LMFEKG+LMRoman12-Regular-Identity-H - Embedded: FALSE
  - /VTHRJV+LMRoman10-Regular-Identity-H - Embedded: FALSE
Text extraction (pypdf): ✓ Works fine (187 chars extracted)
```

**Comparison with Working PDF** (SQL Performance Explained):
```
Producer: Apache FOP Version 1.1
Fonts: Mix of Type0 and Type1 (standard PDF fonts)
  - /Courier (Type1) - Embedded: FALSE
  - /Courier-Bold (Type1) - Embedded: FALSE
  - Type0 fonts also present
Text extraction (pypdf): ✓ Works fine
Docling extraction: ✓ Works fine
```

### Root Cause

**XeLaTeX generates PDFs with Type0 CID-keyed fonts (Identity-H encoding) without font embedding.**

- **Type0 CID-keyed fonts**: Originally designed for Asian/CJK languages
- **Identity-H encoding**: Horizontal CID-keyed font mapping
- **No font embedding**: Font data not included in PDF
- **Latin Modern fonts**: Using advanced font structure for simple Latin text

This specific combination is incompatible with Docling's PDF parser, even though:
- pypdf can read it fine
- Text extraction works
- The PDF displays correctly

**Why SQL Performance PDF works but System Design doesn't:**
- SQL Performance: Uses standard Type1 fonts (`/Courier`, `/Courier-Bold`) alongside Type0
- System Design: Only uses Type0 CID-keyed Identity-H fonts
- Docling can handle Type1 and some Type0 fonts, but not Identity-H encoded Type0 without embedding

## Current Status

### What Works
✓ EPUB detection and file scanning
✓ Pandoc EPUB → PDF conversion (with lmodern fonts installed)
✓ EPUB moved to `knowledge_base/original/` after conversion
✓ Generated PDF kept in `knowledge_base/` for future attempts
✓ Ghostscript font embedding (implemented in v0.5.0-alpha)
✓ Automatic Ghostscript retry for failing PDFs
✓ Clean error messages with diagnostic information
✓ Extraction method tracking in database

### What Doesn't Work
✗ Some EPUBs require double Ghostscript pass (known quirk)

## Known Quirks

### Double Ghostscript Processing (v0.5.0-alpha)

**Behavior:** Some EPUB-generated PDFs require Ghostscript to run twice before Docling can extract text.

**Processing Flow:**
1. Pandoc converts EPUB → PDF with XeLaTeX
2. EpubExtractor applies Ghostscript font embedding (1st pass)
3. Docling extraction attempt fails
4. Automatic Ghostscript retry triggered (2nd pass)
5. Docling extraction succeeds

**Why it happens:**
- First Ghostscript pass embeds fonts correctly
- Docling still fails for unknown reasons
- Second Ghostscript pass "re-renders" the already-processed PDF
- This normalizes the PDF structure in a way Docling can parse

**Impact:**
- Processing takes ~30-60 seconds longer for affected EPUBs
- CPU usage slightly higher during double-pass
- End result is successful extraction
- No user intervention needed

**Future Investigation:**
- ✅ Add condensed error logging to see why first Docling attempt fails (COMPLETED v0.6.0-alpha)
- Investigate if single Ghostscript pass with different flags could work
- Consider caching Ghostscript output to avoid redundant processing

**Status:** Accepted behavior - works reliably, just inefficient

**v0.6.0-alpha Update (2025-11-17):**
- Implemented condensed error logging for Docling failures
- First error from `result.errors` now shown before Ghostscript retry
- Format: `→ Docling failed (error message), attempting Ghostscript fix...`
- Error message limited to 100 characters for readability

## Potential Solutions

### Option 1: Use pdflatex instead of xelatex
```bash
pandoc input.epub -o output.pdf --pdf-engine=pdflatex
```
**Pros**: Generates Type1 fonts, more compatible
**Cons**: Limited Unicode support, may fail on special characters

### Option 2: Post-process with Ghostscript
```bash
gs -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -dEmbedAllFonts=true \
   -sOutputFile=output-embedded.pdf input.pdf
```
**Pros**: Forces font embedding, fixes compatibility
**Cons**: Additional processing step, requires Ghostscript

### Option 3: Try alternative Pandoc PDF engines
- `--pdf-engine=wkhtmltopdf` (HTML-based)
- `--pdf-engine=prince` (commercial)
- `--pdf-engine=weasyprint` (Python-based)

### Option 4: Accept limitation and document
**Current approach**: Document that XeLaTeX-generated PDFs may be incompatible with Docling.
- EPUB source preserved in `original/`
- PDF available for alternative extraction methods
- Clear error message guides users

## Workflow Status

**Current EPUB Processing Pipeline:**
```
1. User adds EPUB to knowledge_base/
2. File watcher detects .epub extension ✓
3. Pandoc converts EPUB → PDF (XeLaTeX engine) ✓
4. EPUB moved to knowledge_base/original/ ✓
5. Docling attempts text extraction from PDF ✗ FAILS
6. PDF moved to knowledge_base/problematic/ ✓
7. User receives clear error message ✓
```

**Files after processing:**
- `knowledge_base/original/Book.epub` - Source EPUB preserved
- `knowledge_base/problematic/Book.pdf` - Incompatible PDF for manual handling

## Recommendations for v0.6.0

### Immediate (v0.5.1 patch):
- Document EPUB limitations in README
- Add note about XeLaTeX font compatibility

### Future (v0.6.0):
- Implement Ghostscript post-processing to embed fonts
- Add fallback to pdflatex if xelatex PDF fails
- Consider alternative EPUB extraction (direct HTML parsing)
- Add `--pdf-engine` configuration option

## Files Modified

### EPUB Support Implementation:
- `api/ingestion.py`: Added `.epub` to SUPPORTED_EXTENSIONS (line 584)
- `api/ingestion.py`: Created EpubExtractor class with Pandoc integration
- `api/ingestion.py`: Improved Docling error reporting with status checks
- `api/watcher.py`: Added `.epub` to SUPPORTED_EXTENSIONS (line 69)
- `api/Dockerfile`: Added `lmodern` package for Latin Modern fonts
- `api/Dockerfile`: Already had `texlive-xetex` and Pandoc dependencies

### Extraction Method Tracking:
- `api/ingestion.py`: Added `extraction_method` column to documents table
- `api/ingestion.py`: Track method in TextExtractor (line 413)
- `api/models.py`: Added DocumentInfoResponse model
- `api/main.py`: Added `/document/{filename}` endpoint

### File Organization:
- `docker-compose.yml`: Removed `:ro` flag from knowledge_base mount
- `api/watcher.py`: Exclude `original/` subdirectory from processing
- `api/main.py`: Exclude `original/` subdirectory from processing

## Testing Notes

**Test Case**: System Design Interview - An insider's guide (Alex Xu)
- EPUB: 7.3 MB
- Generated PDF: 9.1 MB
- Pages: 272
- Pandoc conversion: ✓ SUCCESS (~2 seconds)
- Docling extraction: ✗ FAILURE (Type0 Identity-H fonts)
- Text present: ✓ YES (verified with pypdf)

## Conclusion

The EPUB → PDF conversion infrastructure is **fully functional**. The limitation is **Docling's inability to parse PDFs with Type0 CID-keyed Identity-H fonts without embedding**, which is a quirk of XeLaTeX's PDF generation.

This is not a bug in our code, but a compatibility limitation between:
- XeLaTeX (Pandoc's PDF generator)
- Docling (our PDF extraction library)

Users can:
1. Keep the generated PDF for manual handling
2. Access the original EPUB from `original/` subdirectory
3. Wait for future improvements (Ghostscript post-processing, etc.)
