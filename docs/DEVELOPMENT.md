# Development Guide

This guide covers development workflows, testing, and model experimentation for RAG-KB.

## Architecture

The codebase follows POODR principles with focused, testable modules organized into service layers.

### Directory Structure

```
api/
├── main.py                    # FastAPI application entry point
├── config.py                  # Centralized configuration (type-safe dataclasses)
├── models.py                  # Request/response models
├── ingestion/                 # Document processing pipeline
│   ├── extractors/           # Format-specific extractors (PDF, DOCX, Markdown, etc.)
│   ├── chunkers/             # Chunking strategies (HybridChunker, AST-based, etc.)
│   ├── file_filter.py        # File filtering and exclusion rules
│   └── ...
├── operations/               # API operations layer
│   ├── model_loader.py       # Embedding model management
│   ├── query_executor.py     # Semantic search execution
│   ├── document_lister.py    # Document listing
│   └── ...
├── pipeline/                 # Background processing services
│   ├── pipeline_coordinator.py  # 3-stage concurrent pipeline
│   ├── pipeline_workers.py      # Worker pool implementations
│   ├── indexing_queue.py        # Priority-based queue
│   └── file_watcher.py          # Auto-sync file monitoring
├── startup/                  # Application lifecycle
│   └── manager.py            # StartupManager
└── tests/                    # Test suite (735 tests)
    ├── test_config.py
    ├── test_ingestion.py
    ├── test_main.py
    └── ...
```

### Key Components

**[api/main.py](../api/main.py)** - FastAPI application entry point
- Route handlers for all endpoints
- Application state management
- Background task coordination

**[api/operations/](../api/operations/)** - API operations layer
- Query execution, document management, security operations
- Dependency injection for testability

**[api/pipeline/](../api/pipeline/)** - Background processing
- **PipelineCoordinator**: 3-stage concurrent pipeline (chunk, embed, store)
- **IndexingQueue**: Priority-based queue system (HIGH/NORMAL)
- **FileWatcher**: Auto-sync with debouncing

**[api/ingestion/](../api/ingestion/)** - Document processing
- Format extractors (PDF, DOCX, Markdown, EPUB, Jupyter, Code)
- HybridChunker for documents, AST-based chunking for code
- Vector storage and retrieval

## Running Tests

### Prerequisites

```bash
# Install dependencies
pip install pytest pytest-cov
```

### Run All Tests

```bash
cd api
python -m pytest tests/ -v
```

### Run Specific Test Files

```bash
# Test configuration
python -m pytest tests/test_config.py -v

# Test ingestion
python -m pytest tests/test_ingestion.py -v

# Test API components
python -m pytest tests/test_main.py -v

# Test version consistency
python -m pytest tests/test_version.py -v
```

### Run with Coverage

```bash
python -m pytest tests/ --cov=. --cov-report=term-missing
```

### Test Categories

The test suite includes:

**Unit Tests**:
- Configuration validation (`test_config.py`)
- Document processing (`test_ingestion.py`)
- API components (`test_main.py`)

**Integration Tests**:
- Import verification (`test_query_executor_imports.py`, `test_startup_imports_static.py`)
- Endpoint verification (`test_missing_clear_endpoint.py`)

**Release Verification**:
- Feature completeness (`test_v0_11_0_release_verification.py`)
- Version consistency (`test_version.py`)

## Development Workflow

### 1. Make Changes

Edit files in `api/` directory:

```bash
# Example: Add new feature
vim api/api_services/query_executor.py
```

### 2. Run Tests

```bash
cd api
python -m pytest tests/ -v
```

### 3. Test in Docker

```bash
# Rebuild and start
docker-compose up --build -d

# Check logs
docker-compose logs -f rag-api

# Verify health
curl http://localhost:8000/health
```

### 4. Test Changes

```bash
# Test query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 3}'
```



## Advanced Development Workflows

For maintainers performing advanced operations, see detailed guides in `internal_planning/`:

- **[Blue-Green Deployment](../internal_planning/BLUE_GREEN_DEPLOYMENT.md)** - Side-by-side testing on port 8001 while production runs on port 8000
- **[Model Migration Guide](../internal_planning/MODEL_MIGRATION_GUIDE.md)** - Zero-downtime model migration workflow  
- **[Architecture Decisions](../internal_planning/ARCHITECTURE_DECISIONS.md)** - Technical decisions and rationale

---

## Contributing

When contributing:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all tests pass
5. Update documentation
6. Submit a pull request

See the main [README.md](../README.md) for more information.
