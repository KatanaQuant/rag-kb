"""
Queue routes module

Extracted from main.py following POODR principles:
- Single responsibility: queue operations only
- Dependency injection via FastAPI Request
"""
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


def _validate_indexing_components(app_state):
    """Validate that indexing queue and pipeline are initialized

    Extracted to reduce cyclomatic complexity (Sandi Metz: methods < 5 lines)

    Args:
        app_state: Application state from request

    Raises:
        HTTPException: If components are not initialized
    """
    if not app_state.indexing.queue or not app_state.indexing.worker:
        raise HTTPException(status_code=400, detail="Indexing queue not initialized")

    if not app_state.indexing.pipeline_coordinator:
        raise HTTPException(status_code=400, detail="Concurrent pipeline not initialized")


@router.get("/queue/jobs")
async def get_queue_jobs(request: Request):
    """Get detailed queue and active jobs information

    Shows concurrent pipeline statistics:
    - Input queue size and state
    - Internal pipeline queue sizes (chunk, embed, store)
    - Active jobs in each pipeline stage
    - Worker running status for each stage
    """
    try:
        app_state = request.app.state.app_state
        _validate_indexing_components(app_state)

        # Get pipeline statistics
        pipeline_stats = app_state.indexing.pipeline_coordinator.get_stats()

        return {
            "input_queue_size": app_state.indexing.queue.size(),
            "paused": app_state.indexing.queue.is_paused(),
            "worker_running": app_state.indexing.worker.is_running(),
            "queue_sizes": pipeline_stats["queue_sizes"],
            "active_jobs": pipeline_stats["active_jobs"],
            "workers_running": pipeline_stats["workers_running"]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get queue jobs: {str(e)}")
