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

## Contributing

Found a new issue? Please document it here with:
- Clear description of the problem
- Root cause analysis
- Current impact assessment
- Ideal solution (best case scenario)
- Current workarounds
- Related code/documentation links
