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
- Add to `docs/API.md` if it's an API endpoint
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

## Development Without Disrupting Your Running Instance

**Use Case**: You're using RAG-KB across your network (laptop, phone, IDE integrations) but want to test changes, upgrades, or new features without breaking your daily workflow.

This blue-green deployment approach lets you **use and develop simultaneously** - keep your working instance on port 8000 while testing on port 8001.

### When to Use This Workflow

**Perfect for users who**:
- Use RAG-KB daily across multiple devices
- Want to contribute features or test upgrades
- Need to experiment without disrupting their knowledge base
- Have MCP integrations in VSCode that should stay functional
- Share RAG-KB access with others on their network

**Common development scenarios**:
- **Testing upgrades**: Python 3.11 → 3.13, PyTorch updates, dependency migrations
- **Experimenting with models**: Try different embeddings without reindexing production
- **Feature development**: Build new features while keeping your workflow intact
- **Configuration tuning**: Test chunking strategies, performance settings
- **Contributing back**: Validate changes before submitting PRs

**Why this workflow exists**:
Traditional development requires stopping your instance. But when RAG-KB is integrated into your daily workflow (MCP in VSCode, API queries from scripts, mobile access), downtime is disruptive. This approach eliminates that friction.

**The trade-off**:
Run two instances side-by-side (production on 8000, test on 8001) until you're ready to swap. Only ~10-30 seconds of downtime when you decide to promote your test changes to production.

### Strategy: Side-by-Side Testing

Run the new version on port 8001 while production continues serving on port 8000. Test thoroughly, then swap when ready.

### Step 1: Prepare Changes (No Impact on Production)

Make your changes to Dockerfile, docker-compose.yml, code, or configuration files. You can either:

**Option A: Edit files directly and build with a test tag**
```bash
# Make your changes to Dockerfile, docker-compose.yml, etc.
# Build with a test tag to distinguish from production
docker build -t rag-api:test ./api
```

**Option B: Create variant files for comparison**
```bash
# Keep original files pristine, create test variants
cp api/Dockerfile api/Dockerfile.test
cp docker-compose.yml docker-compose.test.yml

# Edit the .test versions
vim api/Dockerfile.test

# Build from variant
docker build -t rag-api:test -f api/Dockerfile.test ./api
```

<details>
<summary><b>Example: Python 3.13 Version Upgrade</b></summary>

**Changes to api/Dockerfile**:
```dockerfile
FROM python:3.13-slim  # Changed from 3.11-slim

# Update all python3.11 references to python3.13
RUN mkdir -p /usr/local/lib/python3.13/site-packages/deepsearch_glm/resources/models/crf/part-of-speech && \
    mkdir -p /usr/local/lib/python3.13/site-packages/rapidocr/models

RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chown -R appuser:appuser /usr/local/lib/python3.13/site-packages/deepsearch_glm && \
    chown -R appuser:appuser /usr/local/lib/python3.13/site-packages/rapidocr
```

**Changes to docker-compose.yml**:
```yaml
volumes:
  - ./.cache/rapidocr:/usr/local/lib/python3.13/site-packages/rapidocr/models
```
</details>

<details>
<summary><b>Example: Testing a Different Embedding Model</b></summary>

**No code changes needed**, just environment variable:
```bash
# Will set when starting test instance in Step 2
MODEL_NAME=sentence-transformers/static-retrieval-mrl-en-v1
```
</details>

<details>
<summary><b>Example: Experimental Feature Branch</b></summary>

```bash
# Checkout feature branch
git checkout feature/new-chunking-strategy

# Build test image from feature branch code
docker build -t rag-api:test ./api
```
</details>

### Step 2: Start Test Instance on Port 8001 (Parallel to Production)

**Key principle**: Production stays on port 8000 (accessible across your network), test runs on port 8001.

**Option A: Quick start with docker run**
```bash
# Production continues running on port 8000 (unchanged)

# Start test instance on port 8001
docker run -d \
  --name rag-api-test \
  -p 8001:8000 \
  -v ./knowledge_base:/app/knowledge_base \
  -v ./data_test:/app/data \
  -v ./.cache/huggingface:/home/appuser/.cache/huggingface \
  --env-file .env \
  rag-api:test

# Monitor logs
docker logs -f rag-api-test
```

**Option B: Use docker-compose for easier management**

Create `docker-compose.test.yml`:

```yaml
version: '3.8'

services:
  rag-api-test:
    build:
      context: ./api
      dockerfile: Dockerfile  # or Dockerfile.test if using variant
    container_name: rag-api-test
    ports:
      - "8001:8000"  # Test on 8001, production stays on 8000
    volumes:
      # Share knowledge base (read-only, safe for parallel access)
      - ./knowledge_base:/app/knowledge_base

      # IMPORTANT: Use separate database to avoid conflicts
      - ./data_test:/app/data

      # Share model caches (read-only, saves disk space)
      - ./.cache/deepsearch_glm:/app/.cache/deepsearch_glm
      - ./.cache/docling:/home/appuser/.cache/docling
      - ./.cache/huggingface:/home/appuser/.cache/huggingface
      - ./.cache/easyocr:/home/appuser/.EasyOCR
      - ./.cache/rapidocr:/usr/local/lib/python3.11/site-packages/rapidocr/models
    environment:
      - PYTHONUNBUFFERED=1
      # Override any env vars for testing here
      - MODEL_NAME=${TEST_MODEL_NAME:-Snowflake/snowflake-arctic-embed-l-v2.0}
      - BATCH_SIZE=${BATCH_SIZE:-5}
      # ... copy other env vars from main docker-compose.yml
    restart: unless-stopped
```

```bash
# Start test instance
docker-compose -f docker-compose.test.yml up --build -d

# Monitor logs
docker-compose -f docker-compose.test.yml logs -f

# Quick health check
curl http://localhost:8001/health
```

**Network Access Note**:
- Production on port 8000 stays accessible to all network devices
- Test on port 8001 is only accessible from the host machine (or configure firewall for wider access if needed)
- Users/devices continue using production without interruption

### Step 3: Validate Both Instances Running

Verify both instances are healthy and serving independently:

```bash
# Check production (still running on 8000)
curl http://localhost:8000/health | jq

# Check test (new instance on 8001)
curl http://localhost:8001/health | jq

# Compare basic stats
echo "Production documents:"
curl http://localhost:8000/documents | jq '.total'

echo "Test documents:"
curl http://localhost:8001/documents | jq '.total'
```

**What to verify**:
- ** Both return HTTP 200
- ** Both report healthy status
- ** Document counts match (if using same knowledge_base/)
- ** Any version/config differences appear as expected

### Step 4: Run Comparison Tests

**Query Accuracy Test** (same results expected):

```bash
# Query production
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your test query", "top_k": 5}' > prod_results.json

# Query test
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"text": "your test query", "top_k": 5}' > test_results.json

# Compare results
diff prod_results.json test_results.json
```

**Performance Benchmark**:

```bash
# Benchmark production
time curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 5}'

# Benchmark test
time curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"text": "test query", "top_k": 5}'

# Monitor resource usage
docker stats rag-api --no-stream
docker stats rag-api-test --no-stream
```

**Unit Tests**:

```bash
# Run tests in test container
docker exec rag-api-test python -m pytest tests/ -v
```

### Step 5: Swap to New Version (Brief Downtime)

Once validated and ready, perform the swap. **Network users will experience ~10-30 seconds of downtime**.

```bash
# 1. Stop production instance
docker-compose down
# WARNING: Network users lose access here

# 2. Apply your tested changes
# If using variant files:
cp api/Dockerfile.test api/Dockerfile
cp docker-compose.test.yml docker-compose.yml
# Or: Apply changes directly if you edited in place

# 3. Backup current database (safety net)
cp data/rag.db data/rag.db.backup-$(date +%Y%m%d)

# 4. Optional: Copy test database if you want to preserve test indexing
# cp data_test/rag.db data/rag.db

# 5. Rebuild and start on port 8000
docker-compose build --no-cache
docker-compose up -d

# 6. Verify new production is accessible
curl http://localhost:8000/health
# ** Network users can access again

# 7. Monitor for issues
docker-compose logs -f rag-api

# 8. Cleanup test instance when satisfied
docker stop rag-api-test && docker rm rag-api-test
# Or: docker-compose -f docker-compose.test.yml down
rm -rf data_test  # Remove test database
```

**Minimizing downtime tips**:
- Have all files ready before stopping production
- Use `docker-compose build` beforehand if possible
- Keep test instance running until production is verified stable

### Step 6: Rollback (If Needed)

If issues arise after the swap:

```bash
# Stop new version
docker-compose down

# Revert Dockerfile changes
git checkout api/Dockerfile docker-compose.yml

# Restore database backup
mv data/rag.db.backup-YYYYMMDD data/rag.db

# Rebuild with old version
docker-compose build --no-cache
docker-compose up -d

# Verify
curl http://localhost:8000/health
```

### Database Compatibility Notes

**Safe for Side-by-Side Testing**:
- ** **Read-only access**: Both instances can read same `knowledge_base/` directory
- ** **Shared model cache**: Both can share `.cache/huggingface` (read-only)
- ** **Separate databases**: Use `data/` vs `data_test/` to avoid conflicts

**Not Safe for Simultaneous Writes**:
- ** **Same database**: SQLite doesn't handle concurrent writes well
- ** **Same `data/` mount**: Test instance should use separate `data_test/`

**Recommendation**: Test instance should have its own database but can share the knowledge base files (documents are read-only during indexing).

### Pre-Flight Dependency Check (Optional)

Before building Docker images, test dependencies locally:

```bash
# Install Python 3.13 locally (if available)
python3.13 -m venv test-venv-313
source test-venv-313/bin/activate

# Test dependency installation
pip install -r api/requirements.txt

# Run unit tests
cd api
python -m pytest tests/ -v

# Deactivate when done
deactivate
```

### Benefits of This Approach

** **Zero disruption during testing** - Production keeps serving network users
** **A/B comparison** - Direct performance and accuracy comparison
** **Safe experimentation** - Test without risk to production data
** **Network accessibility** - Other devices stay connected to port 8000
** **Confidence before commit** - Thorough validation reduces rollback risk
** **Minimal downtime** - Only ~10-30 seconds during swap

### Real-World Scenarios

**Scenario 1: Testing Python 3.13 Upgrade**
- Production: Python 3.11 on port 8000 (laptops, MCP integrations connected)
- Test: Python 3.13 on port 8001 (validate compatibility, benchmark performance)
- Swap when satisfied, <30 sec downtime for network users

**Scenario 2: Evaluating Different Embedding Model**
- Production: Arctic Embed on port 8000 (serving queries normally)
- Test: Static-retrieval-mrl-en-v1 on port 8001 (test speed vs accuracy tradeoff)
- Compare query results and resource usage before deciding

**Scenario 3: Feature Branch Development**
- Production: Stable release on port 8000 (network-wide access)
- Test: Feature branch on port 8001 (dev testing with production-like data)
- Validate new chunking strategy, async DB migration, etc.

**Scenario 4: Infrastructure Migration**
- Production: Current setup on port 8000 (24/7 availability for network)
- Test: Major dependency update on port 8001 (PyTorch 2.6, FastAPI 0.115)
- Verify no regressions before committing

### Network Access Considerations

**During Testing Phase** (Step 2-4):
- **Port 8000** (Production): Accessible to all network devices, unchanged
- **Port 8001** (Test): Local testing only, or expose to specific devices for validation
- Users continue accessing RAG-KB via MCP, API calls, web queries

**During Swap** (Step 5):
- Brief 10-30 second window where port 8000 is unavailable
- Communicate with network users if timing is critical
- Consider performing swap during low-usage hours

**After Swap**:
- Port 8000 serves new version, network access restored
- Port 8001 can be shut down
- Test artifacts (data_test/) cleaned up

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
