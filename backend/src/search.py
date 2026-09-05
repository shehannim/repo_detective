"""
search.py — Answer natural-language questions about a repository's structure.

Strategy (no LLM required):
  1. Tokenise the question into keywords.
  2. Score every file by:
     a. Keyword match in rel_path / content (TF-style)
     b. In-degree centrality in the dependency graph (heavily imported → important)
     c. PageRank in the dependency graph
  3. Return the top-N files with a brief auto-generated explanation.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List

import networkx as nx

from .ingestion import SourceFile

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_SPLIT = re.compile(r"[^a-zA-Z0-9_]+")

STOP_WORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "with", "this", "that", "it", "its", "what",
    "which", "where", "how", "show", "me", "does", "do", "can", "find",
    "list", "give", "tell", "about", "from", "file", "files", "code",
    "function", "functions", "class", "classes", "module", "modules",
}


def _tokenise(text: str) -> List[str]:
    return [t.lower() for t in _SPLIT.split(text) if len(t) > 1 and t.lower() not in STOP_WORDS]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _content_score(tokens: List[str], sf: SourceFile) -> float:
    """TF score for keyword hits in file path + content."""
    haystack = (sf.rel_path + " " + sf.content).lower()
    score = 0.0
    for tok in tokens:
        count = haystack.count(tok)
        if count:
            score += 1 + math.log(count)   # dampened TF
    return score


def _path_bonus(tokens: List[str], rel_path: str) -> float:
    """Extra weight when keywords appear in the file path."""
    path_lower = rel_path.lower()
    return sum(3.0 for tok in tokens if tok in path_lower)


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------

def _snippet(content: str, tokens: List[str], max_chars: int = 300) -> str:
    """Extract a short snippet around the first keyword hit."""
    lower = content.lower()
    best_pos = len(content)
    for tok in tokens:
        pos = lower.find(tok)
        if 0 <= pos < best_pos:
            best_pos = pos
    if best_pos == len(content):
        return content[:max_chars].strip()
    start = max(0, best_pos - 60)
    end = min(len(content), best_pos + max_chars)
    snippet = content[start:end].strip()
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(content) else "")


def _explain(sf: SourceFile, tokens: List[str], rank: int, score: float,
             indegree: int, G: nx.DiGraph) -> str:
    """Generate a human-readable explanation for why a file was selected."""
    parts: List[str] = []

    # Which keywords hit the path?
    path_hits = [t for t in tokens if t in sf.rel_path.lower()]
    if path_hits:
        parts.append(f"File path matches keyword(s): {', '.join(path_hits)}.")

    # In-degree note
    if indegree > 0:
        parts.append(f"Imported/referenced by {indegree} other file(s) — a central module.")

    # Importees
    importees = list(G.successors(sf.rel_path))
    if importees:
        parts.append(f"Imports {len(importees)} file(s): {', '.join(importees[:3])}"
                     + (" …" if len(importees) > 3 else "."))

    # Snippet
    snippet = _snippet(sf.content, tokens)
    parts.append(f"\nRelevant snippet:\n```\n{snippet}\n```")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SearchResult:
    def __init__(
        self,
        rel_path: str,
        language: str,
        score: float,
        explanation: str,
    ):
        self.rel_path = rel_path
        self.language = language
        self.score = score
        self.explanation = explanation

    def to_dict(self) -> dict:
        return {
            "file": self.rel_path,
            "language": self.language,
            "score": round(self.score, 4),
            "explanation": self.explanation,
        }


def answer_question(
    question: str,
    source_files: List[SourceFile],
    G: nx.DiGraph,
    top_n: int = 5,
) -> List[SearchResult]:
    """
    Return the *top_n* most relevant files for *question*.
    """
    tokens = _tokenise(question)
    if not tokens:
        # Fallback: return the most central files
        tokens = []

    # PageRank (handles disconnected graph gracefully)
    try:
        pagerank: Dict[str, float] = nx.pagerank(G, alpha=0.85)
    except Exception:
        pagerank = {n: 0.0 for n in G.nodes}

    in_degrees: Dict[str, int] = dict(G.in_degree())

    scored: List[tuple[float, SourceFile]] = []
    for sf in source_files:
        content_sc = _content_score(tokens, sf) if tokens else 0.0
        path_sc    = _path_bonus(tokens, sf.rel_path) if tokens else 0.0
        pr_sc      = pagerank.get(sf.rel_path, 0.0) * 50   # scale up PageRank
        indeg_sc   = math.log1p(in_degrees.get(sf.rel_path, 0)) * 5

        total = content_sc + path_sc + pr_sc + indeg_sc
        scored.append((total, sf))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    results: List[SearchResult] = []
    for rank, (score, sf) in enumerate(top, start=1):
        indegree = in_degrees.get(sf.rel_path, 0)
        explanation = _explain(sf, tokens, rank, score, indegree, G)
        results.append(SearchResult(sf.rel_path, sf.language, score, explanation))

    return results
