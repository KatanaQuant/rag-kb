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
│   ├── go_chunker.py         # Go language AST chunker
│   └── ...
├── api_services/             # Application service layer (9 modules)
│   ├── model_loader.py       # Embedding model management
│   ├── file_walker.py        # Directory traversal
│   ├── document_indexer.py   # Document processing orchestration
│   ├── index_orchestrator.py # Index management
│   ├── query_executor.py     # Semantic search execution
│   ├── orphan_detector.py    # Orphan file detection
│   ├── document_lister.py    # Document listing
│   └── document_searcher.py  # Document search
├── services/                 # Core services
│   ├── pipeline_coordinator.py  # 3-stage concurrent pipeline
│   ├── pipeline_workers.py      # Worker pool implementations
│   ├── indexing_queue.py        # Priority-based queue
│   └── file_watcher.py          # Auto-sync file monitoring
├── startup/                  # Application lifecycle
│   └── manager.py            # StartupManager
└── tests/                    # Test suite
    ├── test_config.py
    ├── test_ingestion.py
    ├── test_main.py
    ├── test_version.py
    └── ...
```

### Key Components

**[api/main.py](../api/main.py)** - FastAPI application (530 lines, down from 1246)
- Route handlers for all endpoints
- Application state management
- Background task coordination

**[api/api_services/](../api/api_services/)** - Service layer (9 modules)
- Extracted from main.py following single responsibility principle
- Dependency injection for testability
- Duck typing for flexibility

**[api/services/](../api/services/)** - Core services
- **PipelineCoordinator**: 3-stage concurrent pipeline (chunk → embed → store)
- **IndexingQueue**: Priority-based queue system (HIGH/NORMAL)
- **FileWatcher**: Auto-sync with debouncing

**[api/ingestion/](../api/ingestion/)** - Document processing
- Format extractors (PDF, DOCX, Markdown, Text, EPUB, Jupyter, etc.)
- Semantic chunking with HybridChunker or AST-based chunking
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

## Testing New Models (Without Disrupting Production)

The test instance infrastructure allows safe experimentation on port 8001 while production runs on port 8000.

### Quick Test Workflow

```bash
# 1. Prepare clean test environment
./test-docling-instance.sh nuke  # Remove old test data (prompts for confirmation)

# 2. Add sample documents
cp knowledge_base/some-file.md knowledge_base_test/
# Or create fresh test content

# 3. Start test instance with new model
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1 ./test-docling-instance.sh start

# 4. Check health and stats
./test-docling-instance.sh health

# 5. Test queries
./test-docling-instance.sh query "your test question"

# 6. Compare with production
./test-docling-instance.sh compare

# 7. Monitor resource usage
docker stats rag-api-test --no-stream

# 8. Stop when done
./test-docling-instance.sh stop
```

### Test Instance Commands

```bash
./test-docling-instance.sh start    # Start on port 8001
./test-docling-instance.sh stop     # Stop test instance
./test-docling-instance.sh logs     # View logs
./test-docling-instance.sh health   # Check health status
./test-docling-instance.sh query "text"  # Run test query
./test-docling-instance.sh reindex  # Force reindex
./test-docling-instance.sh clean    # Remove test DB (keeps KB files)
./test-docling-instance.sh nuke     # Remove ALL test data
./test-docling-instance.sh compare  # Compare prod vs test
```

## Model Migration Workflow (Zero-Downtime)

Migrate to a new embedding model without disrupting the running production instance.

### Step-by-Step Migration

```bash
# 1. Test new model first (see above)
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1 ./test-docling-instance.sh start
./test-docling-instance.sh query "test queries..."
# Verify quality meets requirements

# 2. Backup production database
cp data/rag.db data/rag.db.backup-$(date +%Y%m%d)

# 3. Update production configuration
echo "MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1" > .env

# 4. Rebuild production with new model
docker-compose down
rm data/rag.db  # New model requires fresh index
docker-compose up --build -d

# 5. Monitor indexing progress
docker-compose logs -f rag-api | grep -E "Indexed|chunks"

# 6. Verify health
curl http://localhost:8000/health | jq

# 7. Test queries
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 3}' | jq

# 8. Check resource usage
docker stats rag-api --no-stream
```

### Rollback if Needed

```bash
# Stop new model
docker-compose down

# Restore backup
mv data/rag.db.backup-YYYYMMDD data/rag.db

# Revert configuration
git checkout .env  # Or manually set old MODEL_NAME

# Restart with old model
docker-compose up -d
```

## Adding New Features

### Example: Adding a New Endpoint

1. **Define route in main.py**:
```python
@app.post("/my-new-endpoint")
async def my_new_endpoint():
    """My new feature"""
    # Implementation
    return {"status": "success"}
```

2. **Add tests**:
```python
# tests/test_my_feature.py
def test_my_new_endpoint():
    """Test that my new endpoint works"""
    # Test implementation
    pass
```

3. **Update documentation**:
- Add to `docs/OPERATIONAL_CONTROLS.md` if it's an API endpoint
- Add to relevant user-facing docs

4. **Test thoroughly**:
```bash
# Run tests
python -m pytest tests/test_my_feature.py -v

# Test in Docker
docker-compose up --build -d
curl -X POST http://localhost:8000/my-new-endpoint
```

## Performance Profiling

### Monitor Resource Usage

```bash
# Docker stats
docker stats rag-api --no-stream

# Memory usage
docker exec rag-api ps aux | grep python

# Disk usage
du -h data/rag.db
```

### Benchmark Queries

```bash
# Time query execution
time curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 5}'
```

### Log Analysis

```bash
# View indexing performance
docker-compose logs rag-api | grep "Indexed"

# Check for errors
docker-compose logs rag-api | grep -i error

# Monitor queue operations
docker-compose logs rag-api | grep "Queue"
```

## Best Practices

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for function parameters and return values
- Write docstrings for all public functions and classes
- Keep functions focused and single-purpose

### Testing

- Write tests before fixing bugs (TDD approach)
- Test both success and failure cases
- Use meaningful test names that describe what they test
- Keep tests independent and idempotent

### Version Control

- Create feature branches for new work
- Write clear, descriptive commit messages
- Test thoroughly before committing
- Keep commits focused on single changes

### Documentation

- Update docs when adding features
- Include examples for new functionality
- Keep API docs in sync with implementation
- Document configuration options

## Troubleshooting Development Issues

### Docker Build Fails

```bash
# Clean build
docker-compose down
docker system prune -a
docker-compose build --no-cache
docker-compose up -d
```

### Tests Fail in Docker but Pass Locally

Check that Docker container has all dependencies:

```bash
# Exec into container
docker exec -it rag-api bash

# Install test dependencies
pip install pytest pytest-cov

# Run tests
cd /app
python -m pytest tests/ -v
```

### Database Locked Errors

```bash
# Stop all containers
docker-compose down

# Remove lock files
rm data/*.db-*

# Restart
docker-compose up -d
```

## Contributing

When contributing:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all tests pass
5. Update documentation
6. Submit a pull request

See the main [README.md](../README.md) for more information.
