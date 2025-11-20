"""
Query result caching for improved performance
"""
from typing import Dict, List, Optional
from functools import lru_cache
import hashlib
import json

class QueryCache:
    """LRU cache for query results"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.cache: Dict[str, List[Dict]] = {}
        self.access_order: List[str] = []

    def get(self, query: str, top_k: int, threshold: Optional[float]) -> Optional[List[Dict]]:
        """Get cached results if available"""
        key = self._make_key(query, top_k, threshold)
        if key in self.cache:
            self._update_access(key)
            return self.cache[key]
        return None

    def put(self, query: str, top_k: int, threshold: Optional[float], results: List[Dict]):
        """Cache query results"""
        if self.max_size <= 0:
            return

        key = self._make_key(query, top_k, threshold)
        self._evict_if_needed()
        self.cache[key] = results
        self._update_access(key)

    def clear(self):
        """Clear all cached results"""
        self.cache.clear()
        self.access_order.clear()

    def _make_key(self, query: str, top_k: int, threshold: Optional[float]) -> str:
        """Generate cache key"""
        data = {
            'q': query.strip().lower(),
            'k': top_k,
            't': threshold
        }
        content = json.dumps(data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()

    def _update_access(self, key: str):
        """Update LRU access order"""
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

    def _evict_if_needed(self):
        """Evict oldest entry if cache full"""
        if len(self.cache) >= self.max_size and self.access_order:
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
