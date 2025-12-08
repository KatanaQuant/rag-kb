# Domain Glossary

> Ubiquitous Language for RAG-KB

This glossary defines the core terms used throughout the RAG-KB codebase. Using consistent terminology helps developers understand the system and communicate effectively.

---

## Core Terms

| Term | Definition | Bounded Context |
|------|------------|-----------------|
| **Document** | A file indexed for semantic search (PDF, code, markdown, etc.) | Ingestion |
| **Chunk** | A segment of document text with page/position metadata | Pipeline |
| **Embedding** | A dense vector (float[1024]) representing chunk semantics | Pipeline |
| **Query** | A natural language search request | Query |
| **Search Result** | A ranked chunk with relevance score and source metadata | Query |
| **Knowledge Base** | The `kb/` directory containing documents to index | Ingestion |
| **Queue Item** | A document pending processing with assigned priority | Indexing |
| **Processing Result** | Outcome of document processing (success, skipped, failed) | Indexing |

---

## Ingestion Terms

| Term | Definition |
|------|------------|
| **Extraction** | Converting a document file to plain text with metadata |
| **Extractor** | Component that extracts text from a specific file type |
| **Extraction Method** | The strategy used (docling, ast_python, jupyter, etc.) |
| **File Hash** | SHA-256 hash used to detect document changes |
| **Validation** | Security and format checks before processing |
| **Quarantine** | Isolation folder for rejected/suspicious files |

---

## Pipeline Terms

| Term | Definition |
|------|------------|
| **Chunking** | Breaking extracted text into semantically coherent segments |
| **Chunker** | Component that implements a chunking strategy |
| **Hybrid Chunking** | Combining structural and token-based chunking |
| **Semantic Chunking** | Breaking text at natural semantic boundaries |
| **Fixed Chunking** | Breaking text at fixed token intervals |
| **Embedder** | Component that converts text to vector embeddings |
| **Reranker** | Component that re-scores search results for relevance |
| **Pipeline Coordinator** | Orchestrates chunk, embed, and store stages |

---

## Storage Terms

| Term | Definition |
|------|------------|
| **Vector Store** | Database storing embeddings for similarity search |
| **FTS Index** | Full-text search index for keyword matching (PostgreSQL tsvector) |
| **Document Repository** | Persistence layer for document metadata |
| **Chunk Repository** | Persistence layer for chunk content and vectors |
| **Graph Repository** | Persistence layer for Obsidian note relationships |

---

## Database Abstraction Terms

| Term | Definition |
|------|------------|
| **DatabaseFactory** | Factory class for runtime database backend selection (PostgreSQL or SQLite) |
| **OperationsFactory** | Factory class for creating backend-agnostic maintenance operations |
| **HybridSearcher** | ABC interface for combining vector similarity with BM25 keyword search using RRF |

---

## Query Terms

| Term | Definition |
|------|------------|
| **Hybrid Search** | Combining vector similarity and full-text search |
| **top_k** | Maximum number of results to return |
| **Threshold** | Minimum similarity score to include a result |
| **Query Cache** | In-memory cache of recent search results |
| **Reranking** | Re-scoring initial results with a cross-encoder model |

---

## Indexing Terms

| Term | Definition |
|------|------------|
| **Indexing** | The full process: scan, extract, chunk, embed, store |
| **Reindexing** | Re-processing a document (delete + index) |
| **Priority** | Processing urgency: URGENT, HIGH, NORMAL, LOW |
| **Orphan** | Document marked complete but missing from database |
| **Incomplete** | Document that failed mid-processing |
| **File Watcher** | Service that detects file changes in `kb/` |
| **Debounce** | Delay before processing rapid file changes |

---

## Security Terms

| Term | Definition |
|------|------------|
| **Security Scan** | ClamAV + YARA + hash blacklist check |
| **Rejected File** | File that failed validation (quarantined) |
| **Quarantine** | `.quarantine/` folder for suspicious files |
| **Scan Cache** | Cached security scan results by file hash |

---

## Obsidian Terms

| Term | Definition |
|------|------------|
| **Node** | An Obsidian note in the knowledge graph |
| **Edge** | A link relationship between Obsidian notes |
| **Graph-RAG** | Retrieval augmented by note relationships |
| **Vault** | An Obsidian notes directory |

---

## Synonyms to Avoid

| Don't Use | Use Instead | Reason |
|-----------|-------------|--------|
| File | Document | "File" is too generic; "Document" is domain-specific |
| Text | Chunk | "Text" doesn't convey segmentation |
| Vector | Embedding | "Embedding" captures semantic meaning |
| Search | Query | "Query" is the domain action |
| Results | Search Results | Be specific about what results |
| Index | Either "Indexing" (process) or "FTS Index" (structure) | Ambiguous otherwise |

---

*Last updated: 2025-12-08*
