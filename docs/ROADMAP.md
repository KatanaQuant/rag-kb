# RAG Knowledge Base - Roadmap

## Immediate Priorities

### 1. Blog Post Scraper Improvements
**Status:** Planned
**Priority:** High

**Current Issue:**
- Blog posts are scraped as continuous text with no paragraph breaks or structural elements
- Results in poor chunking (entire article becomes 1 chunk)
- No semantic structure preserved

**Required Output Format:**
```markdown
---
title: "Article Title"
author: "Author Name"
date: YYYY-MM-DD
url: https://source.url
tags: ["tag1", "tag2"]
---

# Article Title

Introduction paragraph with proper spacing.

## Section Heading 1

First paragraph of this section.

Second paragraph with blank line separation.

## Section Heading 2

Content here.

### Subsection 2.1

Detailed content.

## Conclusion

Final thoughts.
```

**Key Requirements:**
1. **Headings** - Use `#`, `##`, `###` to create hierarchical structure
2. **Blank lines** - Separate all paragraphs with `\n\n`
3. **YAML frontmatter** - Keep existing metadata format
4. **Structure preservation** - Maintain original article hierarchy

**Benefits:**
- Enables HierarchicalChunker for markdown files
- Better semantic chunking (splits by heading → paragraph → sentence)
- Token-based chunking (respects 512 token limit)
- Preserves context within sections

**Implementation:**
- Update scraper to detect article structure (headings, paragraphs)
- Output properly formatted markdown
- Test with existing blog posts

---

## Completed

### Post v0.5.0-alpha - HierarchicalChunker Fix (2025-11-16)
- ✅ Fixed v0.5.0-alpha latent bugs (HybridChunker doesn't exist in docling 1.20.0)
- ✅ Corrected to use HierarchicalChunker (structure-based chunking)
- ✅ Fixed Docling API usage (DocumentConversionInput.from_paths, conv_result.output)
- ✅ Removed PyPDF/DOCX fallbacks (Docling-only architecture)
- ✅ Increased resource limits (8 CPUs, 16GB RAM)
- ✅ Verbose error logging (traceback.print_exc)
- ✅ EasyOCR model caching documented ("Fetching 10 files" = detection models)

### v0.5.0-alpha - Semantic Chunking & Advanced PDF Processing
- ✅ HierarchicalChunker implementation for PDFs/DOCX
- ✅ OCR support via Tesseract
- ✅ Table structure extraction
- ✅ Semantic chunking configuration (512 token chunks)
- ✅ CPU-optimized Docker build

---

**Last Updated:** 2025-11-16
