import os
import time
from sentence_transformers import SentenceTransformer


def _get_memory_mb() -> float:
    """Get current process memory usage in MB.

    Uses psutil if available, otherwise falls back to /proc on Linux.
    Returns 0.0 if memory cannot be determined.
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        # Fallback for Linux without psutil
        try:
            with open(f'/proc/{os.getpid()}/statm', 'r') as f:
                # First value is total program size in pages
                pages = int(f.read().split()[1])  # RSS is second value
                return pages * os.sysconf('SC_PAGE_SIZE') / 1024 / 1024
        except Exception:
            return 0.0


class ModelLoader:
    """Loads embedding models with retry logic"""

    MAX_RETRIES = 3
    BASE_DELAY = 5  # seconds

    @staticmethod
    def load(model_name: str, max_retries: int = 3) -> SentenceTransformer:
        """Load embedding model with retry on network errors"""
        last_error = None

        for attempt in range(max_retries):
            try:
                # Log memory before load attempt
                mem_mb = _get_memory_mb()
                mem_info = f" [Memory: {mem_mb:.0f}MB]" if mem_mb > 0 else ""
                print(f"Loading model: {model_name}" + (f" (attempt {attempt + 1})" if attempt > 0 else "") + mem_info)
                return SentenceTransformer(model_name)
            except Exception as e:
                last_error = e
                # Log memory on failure for OOM diagnosis
                mem_mb = _get_memory_mb()
                mem_info = f" [Memory: {mem_mb:.0f}MB]" if mem_mb > 0 else ""
                if attempt < max_retries - 1:
                    delay = ModelLoader.BASE_DELAY * (2 ** attempt)  # 5s, 10s, 20s
                    print(f"Model loading failed: {e}{mem_info}")
                    print(f"Retrying in {delay}s...")
                    time.sleep(delay)

        # All retries exhausted - log final memory state
        mem_mb = _get_memory_mb()
        mem_info = f" [Memory at failure: {mem_mb:.0f}MB]" if mem_mb > 0 else ""
        raise RuntimeError(
            f"Failed to load model '{model_name}' after {max_retries} attempts.{mem_info} "
            f"Last error: {last_error}\n"
            f"Hint: If offline, ensure model is cached in .cache/huggingface/ "
            f"or set HF_HUB_OFFLINE=1"
        ) from last_error
