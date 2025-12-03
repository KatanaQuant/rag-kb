"""Indexing routes module."""
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pathlib import Path

from models import IndexRequest, IndexResponse
from config import default_config
from operations.file_walker import FileWalker
from pipeline import Priority
from routes.deps import get_app_state

router = APIRouter()


@router.post("/index", response_model=IndexResponse)
async def index(request_data: IndexRequest, request: Request, background_tasks: BackgroundTasks):
    """Trigger reindexing via queue + concurrent pipeline

    Adds all files to the indexing queue for processing by the
    concurrent pipeline. Returns immediately - check /indexing/status
    or /queue/jobs to monitor progress.

    File scanning happens in background to prevent API blocking.
    """
    try:
        app_state = get_app_state(request)
        if not app_state.get_indexing_queue():
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        # Move file scanning to background to prevent blocking
        def scan_and_queue():
            """Background task: Scan files and add to queue"""
            kb_path = default_config.paths.knowledge_base
            walker = FileWalker(kb_path, app_state.get_processor().SUPPORTED_EXTENSIONS)
            all_files = list(walker.walk())

            priority = Priority.HIGH if request_data.force_reindex else Priority.NORMAL
            app_state.add_many_to_queue(all_files, priority=priority, force=request_data.force_reindex)

            print(f"+ Background scan complete: Queued {len(all_files)} files (force={request_data.force_reindex})")

        background_tasks.add_task(scan_and_queue)

        return IndexResponse(
            status="success",
            indexed_files=0,
            total_chunks=0,
            message=f"File scan started in background (force={request_data.force_reindex}). Check /queue/jobs for progress."
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start indexing: {str(e)}")


@router.post("/indexing/pause")
async def pause_indexing(request: Request):
    """Pause background indexing

    Pauses the indexing worker. Files already being processed will complete,
    but no new files will be processed until resume is called.
    """
    try:
        app_state = get_app_state(request)
        if not app_state.get_indexing_queue():
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        app_state.pause_queue()
        return {
            "status": "success",
            "message": "Indexing paused",
            "queue_size": app_state.queue_size()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause indexing: {str(e)}")


@router.post("/indexing/resume")
async def resume_indexing(request: Request):
    """Resume background indexing

    Resumes the indexing worker to process files from the queue.
    """
    try:
        app_state = get_app_state(request)
        if not app_state.get_indexing_queue():
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        app_state.resume_queue()
        return {
            "status": "success",
            "message": "Indexing resumed",
            "queue_size": app_state.queue_size()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume indexing: {str(e)}")


@router.post("/indexing/clear")
async def clear_indexing_queue(request: Request):
    """Clear pending indexing queue

    Removes all pending files from the indexing queue.
    Files currently being processed will complete.
    """
    try:
        app_state = get_app_state(request)
        if not app_state.get_indexing_queue():
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        app_state.clear_queue()
        return {
            "status": "success",
            "message": "Indexing queue cleared",
            "queue_size": app_state.queue_size()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear queue: {str(e)}")


@router.post("/indexing/priority/{file_path:path}")
async def add_priority_file(file_path: str, request: Request, force: bool = False):
    """Add a file to the front of the indexing queue with high priority

    Args:
        file_path: Relative path from knowledge_base (e.g., "original/test.epub")
        force: Force reindexing even if already indexed

    Use this to prioritize testing or critical files over the background queue.
    """
    try:
        app_state = get_app_state(request)
        if not app_state.get_indexing_queue():
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        # Construct full path
        kb_path = default_config.paths.knowledge_base
        full_path = kb_path / file_path

        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        if not full_path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")

        # Add with high priority
        app_state.add_to_queue(full_path, priority=Priority.HIGH, force=force)

        return {
            "status": "success",
            "message": f"Added {file_path} to queue with HIGH priority",
            "queue_size": app_state.queue_size(),
            "force": force
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add priority file: {str(e)}")


@router.get("/indexing/status")
async def get_indexing_status(request: Request):
    """Get current indexing queue status

    Returns information about the indexing queue and worker state.
    """
    try:
        app_state = get_app_state(request)
        if not app_state.get_indexing_queue() or not app_state.is_worker_running():
            raise HTTPException(status_code=400, detail="Indexing queue not initialized")

        return {
            "queue_size": app_state.queue_size(),
            "paused": app_state.is_queue_paused(),
            "worker_running": app_state.is_worker_running(),
            "indexing_in_progress": app_state.is_indexing_in_progress()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
