import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import threading
from collections import defaultdict

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer

# Models now imported in route modules
from ingestion import DocumentProcessor, VectorStore, ProcessingProgressTracker, FileHasher
from ingestion.file_filter import FileFilterPolicy
from domain_models import DocumentFile
from config import default_config
from watcher import FileWatcherService
from query_cache import QueryCache
from value_objects import IndexingStats, ProcessingResult, DocumentIdentity
from app_state import AppState

# Global state
state = AppState()
from api_services.model_loader import ModelLoader
# API services now imported in route modules
from startup.manager import StartupManager
from routes.health import router as health_router
from routes.query import router as query_router
from routes.indexing import router as indexing_router
from routes.database import router as database_router
from routes.documents import router as documents_router
from routes.queue import router as queue_router
from routes.completeness import router as completeness_router
from routes.security import router as security_router
from routes.maintenance import router as maintenance_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    manager = StartupManager(state)
    await manager.initialize()  # Now async
    yield
    await _cleanup()  # Make cleanup async too

async def _cleanup():
    """Cleanup resources using Law of Demeter compliant delegation"""
    state.stop_watcher()
    state.stop_indexing()
    await state.close_all_resources()  # Now async for AsyncVectorStore

app = FastAPI(
    title="RAG Knowledge Base API",
    description="Local RAG system for querying your knowledge base",
    version="0.15.0-alpha",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store state in app for route access
app.state.app_state = state

# Include route modules
app.include_router(health_router)
app.include_router(query_router)
app.include_router(indexing_router)
app.include_router(database_router)
app.include_router(documents_router)
app.include_router(queue_router)
app.include_router(completeness_router)
app.include_router(security_router)
app.include_router(maintenance_router)

# All routes extracted to routes/ modules following POODR principles
# - routes/health.py: Health and info endpoints
# - routes/query.py: Query operations
# - routes/indexing.py: Indexing operations (6 endpoints)
# - routes/database.py: Database maintenance (3 endpoints)
# - routes/documents.py: Document management (4 endpoints)
# - routes/queue.py: Queue monitoring (1 endpoint)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

