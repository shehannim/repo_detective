"""
cache.py — Simple in-process LRU cache for analysed repositories.

Keyed by repo URL. Stores (source_files, dependency_graph) so repeated
questions about the same repo don't trigger a fresh clone.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import List, NamedTuple, Optional, Tuple

import networkx as nx

from .ingestion import SourceFile


class CacheEntry(NamedTuple):
    source_files: List[SourceFile]
    graph: nx.DiGraph
    repo_root: str          # temp dir path (so it can be cleaned up on eviction)
    ingested_at: float      # epoch seconds


class RepoCache:
    """Thread-unsafe in-process LRU cache (suitable for single-worker Uvicorn)."""

    def __init__(self, max_size: int = 5, ttl_seconds: int = 3600):
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, repo_url: str) -> Optional[CacheEntry]:
        if repo_url not in self._store:
            return None
        entry = self._store[repo_url]
        if time.time() - entry.ingested_at > self._ttl:
            self._store.pop(repo_url, None)
            return None
        # Move to end (most recently used)
        self._store.move_to_end(repo_url)
        return entry

    def put(self, repo_url: str, entry: CacheEntry) -> None:
        if repo_url in self._store:
            self._store.move_to_end(repo_url)
        self._store[repo_url] = entry
        while len(self._store) > self._max_size:
            # Evict least recently used
            _, evicted = self._store.popitem(last=False)
            # Optionally clean up temp dir
            try:
                import shutil
                shutil.rmtree(evicted.repo_root, ignore_errors=True)
            except Exception:
                pass

    def invalidate(self, repo_url: str) -> None:
        self._store.pop(repo_url, None)

    def stats(self) -> dict:
        return {
            "cached_repos": list(self._store.keys()),
            "size": len(self._store),
            "max_size": self._max_size,
        }


# Singleton used by the FastAPI app
repo_cache = RepoCache(max_size=5, ttl_seconds=3600)
