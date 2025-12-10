import time
from sentence_transformers import SentenceTransformer


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
                print(f"Loading model: {model_name}" + (f" (attempt {attempt + 1})" if attempt > 0 else ""))
                return SentenceTransformer(model_name)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = ModelLoader.BASE_DELAY * (2 ** attempt)  # 5s, 10s, 20s
                    print(f"Model loading failed: {e}")
                    print(f"Retrying in {delay}s...")
                    time.sleep(delay)

        # All retries exhausted
        raise RuntimeError(
            f"Failed to load model '{model_name}' after {max_retries} attempts. "
            f"Last error: {last_error}\n"
            f"Hint: If offline, ensure model is cached in .cache/huggingface/ "
            f"or set HF_HUB_OFFLINE=1"
        ) from last_error
