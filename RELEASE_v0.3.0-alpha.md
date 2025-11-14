# Release v0.3.0-alpha - Automatic File Watching

**Release Date**: 2025-11-14
**Type**: Alpha Release
**Focus**: Real-Time Document Indexing

---

## 🎉 Major Features

### Automatic File Watching & Real-Time Indexing

The system now automatically detects and indexes new or modified files in the `knowledge_base/` directory without requiring a container restart!

**Key Benefits:**
- ✅ **Zero-restart indexing** - Just drop files and they're searchable
- ✅ **Smart debouncing** - Handles bulk operations efficiently (git pull, mass file copies)
- ✅ **Production-tested** - Verified with real workloads, no crashes or errors
- ✅ **Fully configurable** - Fine-tune debounce timing and batch sizes

**How it works:**
- File watcher monitors `knowledge_base/` directory recursively
- Changes are collected for 10 seconds (configurable) to batch operations
- After quiet period, all changes are indexed together
- Handles text editor save patterns, git operations, and bulk imports gracefully

**Configuration:**
```bash
# .env file
WATCH_ENABLED=true                  # Enable/disable auto-sync (default: true)
WATCH_DEBOUNCE_SECONDS=10.0         # Wait time after last change (default: 10.0)
WATCH_BATCH_SIZE=50                 # Max files per batch (default: 50)
```

---

## 📝 Changes

### Added
- New `api/watcher.py` module (177 lines, 7 focused classes)
  - `DebounceTimer` - Manages timing for event batching
  - `FileChangeCollector` - Thread-safe event collection
  - `DocumentEventHandler` - Handles filesystem events
  - `IndexingCoordinator` - Processes collected changes
  - `FileWatcherService` - Main orchestrator
- `WatcherConfig` dataclass in `api/config.py`
- 17 comprehensive unit tests in `api/tests/test_watcher.py`
- Auto-sync documentation in README.md
- Configuration examples in `.env.example`

### Changed
- Updated `api/main.py` - Integrated watcher into FastAPI lifespan
- Updated `api/config.py` - Added watcher configuration
- Updated `api/tests/test_config.py` - Enhanced for watcher config testing
- Updated README.md - Added "Auto-Sync Configuration" section
- Updated `.env.example` - Added watcher configuration examples

### Fixed
- Resolved "No Real-Time Indexing" issue (previously required restart)

---

## 🧪 Testing

- **Unit Tests**: 17 new tests, all passing
- **Integration Tests**: Production verified with real files
- **Test Coverage**: 50+ tests across all modules
- **Security Audit**: ✅ Thread-safe, no vulnerabilities

**Production Verification:**
- ✅ System startup successful (Arctic Embed model loaded)
- ✅ Initial indexing: 2 docs, 365 chunks
- ✅ File watcher started successfully
- ✅ Real-time detection: Files indexed in <10s
- ✅ Query verification: Auto-indexed content searchable via API
- ✅ No errors or crashes during operation

---

## 🏗️ Architecture

**Design Decisions:**
- **Observer pattern with debouncing** for robustness
- **Thread-safe collections** to prevent race conditions
- **Graceful degradation** - errors don't stop the watcher
- **10s debounce** balances responsiveness with batching efficiency

**Sandi Metz Compliance:**
- All classes ≤ 100 lines
- All methods ≤ 5 lines
- Single Responsibility Principle throughout

---

## 📦 Installation

### Upgrading from v0.2.0-alpha

```bash
cd rag-kb
git pull origin main
git checkout v0.3.0-alpha
docker-compose down
docker-compose up -d --build
```

### Fresh Install

```bash
git clone https://github.com/KatanaQuant/rag-kb.git
cd rag-kb
git checkout v0.3.0-alpha
docker-compose up -d
```

---

## ⚠️ Breaking Changes

None. This release is fully backward compatible with v0.2.0-alpha.

---

## 🐛 Known Issues

1. **Manual MCP Server Startup** (P3 - Nuisance)
   - Must manually activate via "MCP: List Servers" after VSCode restart
   - Workaround: Run command after VSCode opens

---

## 📊 Stats

- **Lines of Code**: +524 additions, -6 deletions
- **New Files**: 2 (watcher.py, test_watcher.py)
- **Modified Files**: 5 (config.py, main.py, test_config.py, README.md, .env.example)
- **Test Coverage**: 50+ tests (17 new)
- **Classes Added**: 7 focused classes
- **Dependencies**: No new dependencies (watchdog already included)

---

## 🙏 Credits

Built with:
- **FastAPI** - Modern web framework
- **watchdog** - Cross-platform file system monitoring
- **sqlite-vec** - Vector similarity search
- **sentence-transformers** - Embedding models

---

## 🔗 Resources

- **Repository**: https://github.com/KatanaQuant/rag-kb
- **Documentation**: [README.md](README.md)
- **Previous Release**: [v0.2.0-alpha](https://github.com/KatanaQuant/rag-kb/releases/tag/v0.2.0-alpha)

---

**Ready to use!** Drop files into `knowledge_base/` and watch them get indexed automatically. 🚀
