# Known Issues

This document tracks known issues, limitations, and their workarounds.

## 1. HybridChunker Can Exceed Model's Max Sequence Length

**Issue:** Docling's HybridChunker with `merge_peers=True` can create chunks that exceed the embedding model's maximum sequence length, resulting in warning messages like:

```
Token indices sequence length is longer than the specified maximum sequence length for this model (8202 > 8192). Running this sequence through the model will result in indexing errors
```

**Root Cause:**
- HybridChunker doesn't strictly enforce the `max_tokens` parameter ([docling-core#119](https://github.com/docling-project/docling-core/issues/119))
- When `merge_peers=True`, adjacent chunks with the same metadata are merged, potentially exceeding the token limit
- Long sentences or paragraphs remain unsplit even when they exceed the limit

**Current Impact:**
- ⚠️ **Minimal**: sentence-transformers automatically truncates oversized chunks
- Affects ~10-40 characters at the end of oversized chunks
- System continues to function normally

**Affected Configuration:**
- Models with sequence length limits (e.g., `Snowflake/snowflake-arctic-embed-l-v2.0` has 8192 token limit)
- `SEMANTIC_CHUNKING=true` (uses HybridChunker)
- Large documents with mergeable adjacent chunks

**Ideal Solution (Best Case Scenario):**

The system should handle this in layers:

1. **Prevention Layer** (Chunking):
   - HybridChunker should strictly enforce max_tokens before merging
   - OR set `CHUNK_MAX_TOKENS` to ~75% of model's limit (e.g., 6000 for 8192-token models)
   - Validate chunk sizes after merging and split oversized chunks

2. **Detection Layer** (Pre-embedding):
   ```python
   # Before encoding, validate chunk sizes
   def validate_chunk_sizes(chunks, model_max_length):
       for chunk in chunks:
           token_count = count_tokens(chunk['content'])
           if token_count > model_max_length:
               # Option A: Split oversized chunk
               # Option B: Log warning with chunk metadata
               # Option C: Truncate with explicit marker
   ```

3. **Graceful Handling Layer** (Embedding):
   ```python
   # Explicitly configure model truncation behavior
   model.max_seq_length = 8192
   embeddings = model.encode(
       texts,
       show_progress_bar=False,
       truncate_dim=model.max_seq_length  # Explicit truncation
   )
   ```

4. **Observability Layer**:
   - Log which documents/chunks were truncated
   - Track truncation metrics (frequency, token count distribution)
   - Alert if truncation rate exceeds threshold

**Current Workaround:**

Option 1 (Recommended): Accept automatic truncation
- No changes needed
- sentence-transformers handles it gracefully
- Minimal information loss (~10 tokens per affected chunk)

Option 2: Add explicit model configuration (prevents warning):
```python
# In api/main.py ModelLoader.load()
model = SentenceTransformer(model_name)
model.max_seq_length = 8192  # Match model's limit
```

Option 3: Lower CHUNK_MAX_TOKENS (requires re-indexing):
```bash
# In .env
CHUNK_MAX_TOKENS=6000  # Leave buffer for merge_peers
```

**Status:** Accepted limitation until docling-core#119 is resolved

**Related:**
- [Docling HybridChunker Issue #119](https://github.com/docling-project/docling-core/issues/119)
- [config.py:28](../api/config.py#L28) - CHUNK_MAX_TOKENS default
- [extractors.py:81-87](../api/ingestion/extractors.py#L81-L87) - HybridChunker initialization

---

## 2. TextExtractor Naming is Misleading

**Issue:** The `TextExtractor` class ([api/ingestion/extractors.py:630](../api/ingestion/extractors.py#L630)) is named like a specific extractor, but it's actually a **router/coordinator** that delegates to specialized extractors.

**Current Behavior:**
```python
TextExtractor routes to:
├─→ DoclingExtractor      (PDF, DOCX)
├─→ EpubExtractor         (EPUB)
├─→ MarkdownExtractor     (regular .md)
├─→ ObsidianExtractor     (Obsidian .md with wikilinks/tags)
├─→ CodeExtractor         (code files with AST chunking)
└─→ JupyterExtractor      (notebooks with cell-aware chunking)
```

**Impact:** Minor - naming confusion for developers reading the code

**Ideal Solution:**
Rename to `ExtractionRouter` or `ExtractorCoordinator` to make intent clear

**Current Workaround:** None needed - code functions correctly, just naming is misleading

**Status:** Accepted cosmetic issue - low priority refactor

**Related:**
- [extractors.py:630](../api/ingestion/extractors.py#L630) - TextExtractor class definition
- [processing.py:151](../api/ingestion/processing.py#L151) - DocumentProcessor uses TextExtractor

---

## 3. Extraction Method Logging Shows Incorrect Method

**Issue:** The extraction method logged in processing output can show the wrong method. For example, a PDF processed with Docling may be logged as `obsidian_graph_rag`.

**Example:**
```
Extraction complete (obsidian_graph_rag): UNIX and Linux System Administration.pdf - 2,870,514 chars extracted
```

**Root Cause:**
The `TextExtractor.last_method` instance variable ([extractors.py:635](../api/ingestion/extractors.py#L635)) persists between file processing calls. If a markdown file sets `last_method = 'obsidian_graph_rag'` and the next file is a PDF, the old value may be displayed even though the PDF actually used Docling.

The method tracking happens at [extractors.py:665](../api/ingestion/extractors.py#L665):
```python
self.last_method = method_map.get(ext, 'unknown')
return self.extractors[ext](file_path)
```

However, the special markdown handling path ([extractors.py:647-648](../api/ingestion/extractors.py#L647-L648)) calls `_extract_markdown_intelligently()` which may set `last_method` differently, and this value can persist.

**Current Impact:**
- ⚠️ **Cosmetic only**: Only affects log output
- **No functional impact**: The correct extractor is always called
- **No data corruption**: Chunks are processed correctly regardless of log message
- Can confuse developers debugging extraction issues

**Evidence of Correct Behavior:**
- File extension routing always calls correct extractor ([extractors.py:691](../api/ingestion/extractors.py#L691))
- Processing time matches expected method (2.5 hours for 54MB PDF is Docling-typical)
- Character counts match expected extraction method

**Ideal Solution:**
Reset `self.last_method = None` at the start of each `extract()` call, or better yet, return the method name directly from the extraction result instead of using instance state:

```python
def extract(self, file_path: Path) -> ExtractionResult:
    ext = file_path.suffix.lower()
    # Determine method first
    if ext in ['.md', '.markdown']:
        return self._extract_markdown_intelligently(file_path)

    method = self.method_map.get(ext, 'unknown')
    result = self.extractors[ext](file_path)
    result.method = method  # Set method in result, not instance var
    return result
```

**Current Workaround:**
Be aware that logged extraction methods may not match actual methods used. Cross-reference with:
- File extension (`.pdf` → docling, `.md` → markdown/obsidian, `.py` → AST)
- Processing time (hours → Docling, seconds/minutes → markdown/code)
- Character count patterns

**Status:** Low priority cosmetic bug - does not affect functionality

**Related:**
- [extractors.py:635](../api/ingestion/extractors.py#L635) - TextExtractor.last_method declaration
- [extractors.py:641-667](../api/ingestion/extractors.py#L641-L667) - extract() method with method tracking
- [processing.py:255-257](../api/ingestion/processing.py#L255-L257) - Log output using get_last_method()

---

## Contributing

Found a new issue? Please document it here with:
- Clear description of the problem
- Root cause analysis
- Current impact assessment
- Ideal solution (best case scenario)
- Current workarounds
- Related code/documentation links
