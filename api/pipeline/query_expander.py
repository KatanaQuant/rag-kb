"""LLM-based query expansion using Ollama.

Generates alternative phrasings of user queries to improve retrieval.
Based on LangChain's MultiQueryRetriever pattern.

Expected improvement: +10-15% retrieval accuracy (per Azure research).
"""

import os
import json
import logging
import hashlib
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Prompt for query expansion
EXPANSION_PROMPT = """You are a search query optimizer. Given a user's search query, generate 2-3 alternative phrasings that might find the same content in a document database.

Rules:
- Keep alternatives concise (3-8 words each)
- Focus on synonyms and related terms
- Include the main concepts from the original query
- Don't add new topics not in the original query

User query: {query}

Return ONLY a JSON array of alternative queries, no explanation:
["alternative 1", "alternative 2", "alternative 3"]"""


class QueryExpander:
    """Expands search queries using Ollama LLM."""

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        cache_dir: Optional[str] = None,
        enabled: bool = True
    ):
        self.ollama_url = ollama_url or os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.model = model or os.getenv("QUERY_EXPANSION_MODEL", "qwen2.5:0.5b")
        self.enabled = enabled and os.getenv("QUERY_EXPANSION_ENABLED", "false").lower() == "true"

        # Cache for expanded queries (use /app/data for persistence via volume mount)
        self.cache_dir = Path(cache_dir or "/app/data/query_expansion")
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._available = None  # Lazy check

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key for a query."""
        return hashlib.md5(f"{self.model}:{query}".encode()).hexdigest()

    def _get_cached(self, query: str) -> Optional[List[str]]:
        """Get cached expansion for a query."""
        if not self.enabled:
            return None
        cache_file = self.cache_dir / f"{self._get_cache_key(query)}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _set_cached(self, query: str, expansions: List[str]):
        """Cache expansions for a query."""
        if not self.enabled:
            return
        cache_file = self.cache_dir / f"{self._get_cache_key(query)}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(expansions, f)
        except Exception as e:
            logger.warning(f"Failed to cache query expansion: {e}")

    def _check_availability(self) -> bool:
        """Check if Ollama is available and model is loaded."""
        if self._available is not None:
            return self._available

        try:
            import requests
            # Check if Ollama is running
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            if response.status_code != 200:
                self._available = False
                return False

            # Check if model is available
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Check for exact match or prefix match (e.g., "qwen2.5:0.5b" matches "qwen2.5:0.5b-instruct")
            self._available = any(
                self.model in name or name.startswith(self.model.split(":")[0])
                for name in model_names
            )

            if not self._available:
                logger.warning(
                    f"Query expansion model '{self.model}' not found. "
                    f"Available: {model_names}. Run: docker exec ollama ollama pull {self.model}"
                )

            return self._available
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            self._available = False
            return False

    def expand(self, query: str) -> List[str]:
        """Expand a query into alternative phrasings.

        Returns:
            List of alternative queries (may include original).
            Returns [query] if expansion fails or is disabled.
        """
        if not self.enabled:
            return [query]

        # Check cache first
        cached = self._get_cached(query)
        if cached:
            logger.debug(f"Cache hit for query: {query[:50]}...")
            return [query] + cached

        # Check Ollama availability
        if not self._check_availability():
            return [query]

        try:
            import requests

            prompt = EXPANSION_PROMPT.format(query=query)
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,  # Low for consistent outputs
                        "num_predict": 100,  # Short response expected
                    }
                },
                timeout=10
            )

            if response.status_code != 200:
                logger.warning(f"Ollama API error: {response.status_code}")
                return [query]

            result = response.json().get("response", "")

            # Parse JSON response
            try:
                # Find JSON array in response
                start = result.find("[")
                end = result.rfind("]") + 1
                if start >= 0 and end > start:
                    expansions = json.loads(result[start:end])
                    if isinstance(expansions, list) and all(isinstance(e, str) for e in expansions):
                        # Cache and return
                        self._set_cached(query, expansions)
                        logger.info(f"Expanded '{query[:30]}...' into {len(expansions)} variants")
                        return [query] + expansions
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse expansion response: {result[:100]}")

            return [query]

        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return [query]

    @property
    def is_enabled(self) -> bool:
        return self.enabled and self._check_availability()
