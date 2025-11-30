# Known Issues

Active issues and limitations in RAG-KB.

---

## Summary

**Critical Issues**: None
**Active Limitations**: GIL contention (CPU-only), .md chunking coherence (needs reindex)
**Planned Fixes**: v2.0.0 GPU support addresses performance, semantic chunking improves coherence

---

## Active Issues

### 1. GIL Contention with Multiple Embedding Workers

**Severity**: LOW | **Fix**: v2.0.0 GPU support

Multiple embedding workers don't scale linearly due to Python's GIL. Current workaround: `BatchEncoder` provides 10-50x throughput improvement. Config: `EMBEDDING_WORKERS=2`, `EMBEDDING_BATCH_SIZE=32`.

---

### 2. Markdown File Chunking Quality

**Severity**: LOW | **Fix**: Reindex .md files

Older .md files (pre-v1.7.2) may have lower coherence. Reindex to improve from ~42% to ~65-85%:

```bash
curl -X POST 'http://localhost:8000/documents/reindex?force=true&filter=.md'
```

---

### 3. EPUB Orphan Detection False Positive

**Severity**: LOW | Cosmetic only

Converted EPUBs logged as "orphaned" during startup, but correctly cleaned up. No action needed.

---

### 4. EPUB E2E Testing

**Severity**: LOW | Workflow note

EPUBs bypass chunking pipeline - only converted PDF gets indexed. Delete old PDF before E2E testing.

**Details**: [internal_planning/EPUB_E2E_TESTING.md](../internal_planning/EPUB_E2E_TESTING.md)

---

### 5. Test Limitations

- **API Mock Recursion**: `test_delete_document_success` skipped (FastAPI JSON encoder issue)
- **Transaction Tests**: `TestDatabaseTransactions` skipped (VectorStore uses auto-commit)

---

## Contributing

Found an issue? Document with: description, root cause, impact, workaround.
