"""
qa_engine.py — LLM-powered reasoning layer for repo-detective.

Architecture
------------
1. keyword/graph ranking  → rank_candidates via search.answer_question()
2. build_llm_context()    → grounded prompt for general /ask questions
   build_issue_llm_context() → grounded prompt for GitHub issue triage
3. stream_answer()        → async NDJSON generator (shared by /ask and /issue):
     {"type":"step",   "message":"...", "ts": float}
     {"type":"result", "data": {...},   "ts": float}

LLM backend priority
--------------------
1. ANTHROPIC_API_KEY → Claude (claude-3-5-haiku-20241022 by default)
2. QWEN_API_KEY    → Qwen via Google AI Studio
3. ADC              → Qwen via Vertex AI
4. fallback          → keyword/graph only (used_llm=False)

Environment variables
---------------------
ANTHROPIC_API_KEY      — Anthropic API key
ANTHROPIC_MODEL        — Claude model (default: claude-3-5-haiku-20241022)
QWEN_API_KEY         — Google AI Studio key
QWEN_MODEL           — Qwen model (default: qwen-max)
REPO_DET_CONTENT_CHARS — Max chars of each file sent to LLM (default: 3000)
REPO_DET_LLM_TOP_K     — Candidate files sent to LLM (default: 5)
REPO_DET_LLM_TIMEOUT   — Request timeout seconds (default: 30)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncGenerator, List, Literal, Optional

import networkx as nx

from .graph import graph_summary
from .ingestion import SourceFile
from .search import SearchResult, answer_question

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
_QWEN_MODEL    = os.getenv("QWEN_MODEL",    "qwen-max")
_CONTENT_CHARS   = int(os.getenv("REPO_DET_CONTENT_CHARS", "3000"))
_LLM_TOP_K       = int(os.getenv("REPO_DET_LLM_TOP_K", "5"))
_LLM_TIMEOUT     = float(os.getenv("REPO_DET_LLM_TIMEOUT", "30.0"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(start: float) -> float:
    return round(time.perf_counter() - start, 3)

def _ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"

def _step(msg: str, start: float) -> str:
    return _ndjson({"type": "step", "message": msg, "ts": _ts(start)})


# ---------------------------------------------------------------------------
# LLM client factory
# ---------------------------------------------------------------------------

def _make_client() -> tuple[object | None, Literal["anthropic", "qwen", "none"]]:
    """
    Return (client, backend_name).
    Tries Anthropic → Alibaba Cloud → Vertex ADC → gives up.
    """
    # 1. Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        try:
            import anthropic  # type: ignore[import]
            return anthropic.Anthropic(api_key=anthropic_key), "anthropic"
        except Exception as exc:
            logger.warning("Anthropic init failed: %s", exc)

    # 2. Alibaba Cloud
    qwen_key = os.getenv("QWEN_API_KEY", "").strip()
    if qwen_key:
        try:
            from google import genai  # type: ignore[import]
            return genai.Client(api_key=qwen_key), "qwen"
        except Exception as exc:
            logger.warning("Alibaba Cloud init failed: %s", exc)

    # 3. Vertex AI via ADC
    try:
        import google.auth                            # type: ignore[import]
        import google.auth.transport.requests         # type: ignore[import]
        from google import genai                      # type: ignore[import]
        creds, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        return genai.Client(
            vertexai=True, project=project,
            location=location, credentials=creds,
        ), "qwen"
    except Exception:
        pass

    return None, "none"


# ---------------------------------------------------------------------------
# Shared candidate-block builder
# ---------------------------------------------------------------------------

def _candidate_blocks(
    candidates: List[SearchResult],
    source_map: dict[str, SourceFile],
    G: nx.DiGraph,
    in_deg: dict[str, int],
) -> list[str]:
    blocks: list[str] = []
    for rank, cand in enumerate(candidates, 1):
        sf        = source_map.get(cand.rel_path)
        preview   = (sf.content[:_CONTENT_CHARS] + "\n…[truncated]") if sf else "(unavailable)"
        importers = list(G.predecessors(cand.rel_path))
        importees = list(G.successors(cand.rel_path))
        blocks.append(
            f"### Candidate {rank}: `{cand.rel_path}`\n"
            f"**Lang:** {cand.language} | "
            f"**Score:** {cand.score:.4f} | "
            f"**Imported by {in_deg.get(cand.rel_path, 0)} file(s):** "
            f"{', '.join(f'`{p}`' for p in importers[:4]) or 'none'}\n"
            f"**Imports:** {', '.join(f'`{i}`' for i in importees[:4]) or 'none'}\n\n"
            f"```\n{preview}\n```\n\n"
        )
    return blocks


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_llm_context(
    question: str,
    candidates: List[SearchResult],
    source_map: dict[str, SourceFile],
    G: nx.DiGraph,
) -> str:
    """General /ask prompt — explains which files answer a free-form question."""
    gsum   = graph_summary(G)
    in_deg = dict(G.in_degree())

    parts = [
        "You are a senior software engineer doing a code-structure deep dive.\n\n"
        "STRICT RULES:\n"
        "• Base your answer ONLY on the file content excerpts provided below.\n"
        "• Do NOT invent file names, functions, or classes not visible in the excerpts.\n"
        "• Quote exact symbols or line fragments from the excerpts when citing evidence.\n\n",

        f"## Question\n{question}\n\n",

        f"## Repository snapshot\n"
        f"- Source files: {gsum['nodes']}  |  Import edges: {gsum['edges']}\n"
        f"- Languages: {', '.join(gsum['languages'])}\n"
        f"- Most-imported: {', '.join(gsum['top_imported'][:5])}\n\n",

        "## Candidate files (ranked by keyword + PageRank score)\n\n",
        *_candidate_blocks(candidates, source_map, G, in_deg),

        "## Required response format\n"
        "1. **Primary answer** – Name the single most relevant file and explain "
        "WHY, quoting specific code from its excerpt.\n"
        "2. **Supporting files** – For each other candidate, one sentence on "
        "its role, with a specific code reference.\n"
        "3. **Key entry points** – List 2–5 exact function/class names a "
        "developer should look at first, drawn only from the excerpts above.\n",
    ]
    return "".join(parts)


def build_issue_llm_context(
    issue_title: str,
    issue_body: str,
    issue_number: Optional[int],
    candidates: List[SearchResult],
    source_map: dict[str, SourceFile],
    G: nx.DiGraph,
) -> str:
    """
    Issue-triage prompt — identifies which files are most likely responsible
    for a bug or feature request described in a GitHub issue.
    """
    gsum   = graph_summary(G)
    in_deg = dict(G.in_degree())

    issue_ref    = f"Issue #{issue_number}: " if issue_number else ""
    body_excerpt = issue_body[:2500] + ("\n…[truncated]" if len(issue_body) > 2500 else "")

    parts = [
        "You are an expert software maintainer doing issue triage.\n\n"
        "STRICT RULES:\n"
        "• Base your answer ONLY on the file content excerpts provided below.\n"
        "• Do NOT invent file names, functions, or classes not visible in the excerpts.\n"
        "• Quote exact symbols or line fragments when citing evidence.\n\n",

        f"## GitHub Issue\n"
        f"**{issue_ref}{issue_title}**\n\n"
        f"{body_excerpt}\n\n",

        f"## Repository snapshot\n"
        f"- Source files: {gsum['nodes']}  |  Import edges: {gsum['edges']}\n"
        f"- Languages: {', '.join(gsum['languages'])}\n"
        f"- Most-imported files: {', '.join(gsum['top_imported'][:5])}\n\n",

        "## Candidate files (ranked by keyword + PageRank score)\n\n",
        *_candidate_blocks(candidates, source_map, G, in_deg),

        "## Required triage response format\n"
        "1. **Most likely location** – The single file most likely to contain the bug "
        "or require the change. Explain WHY using evidence from its excerpt.\n"
        "2. **Supporting files** – Other files a developer should review, each with "
        "a one-sentence reason and a specific code reference.\n"
        "3. **Suggested fix area** – Exact function(s) or class(es) where the change "
        "should be made, citing only symbols visible in the excerpts.\n"
        "4. **Relevant tests** – If any test files appear among the candidates, note them.\n",
    ]
    return "".join(parts)


# ---------------------------------------------------------------------------
# LLM call dispatcher
# ---------------------------------------------------------------------------

def _call_llm(client: object, backend: str, prompt: str) -> str:
    if backend == "anthropic":
        import anthropic  # type: ignore[import]
        msg = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
            timeout=_LLM_TIMEOUT,
        )
        return msg.content[0].text

    if backend == "qwen":
        resp = client.models.generate_content(model=_QWEN_MODEL, contents=prompt)
        return resp.text

    raise RuntimeError("Unknown backend")


# ---------------------------------------------------------------------------
# Public streaming generator  (shared by /ask AND /issue)
# ---------------------------------------------------------------------------

async def stream_answer(
    question: str,
    source_files: List[SourceFile],
    G: nx.DiGraph,
    top_n: int = 5,
    graph_sum: dict | None = None,
    # Issue-triage extras — when set, switches to issue prompt + step labels
    issue_title: str | None = None,
    issue_body: str | None = None,
    issue_number: int | None = None,
) -> AsyncGenerator[str, None]:
    """
    Async NDJSON generator shared by /ask and /issue endpoints.

    Step events  → {"type":"step",   "message":"...", "ts": float}
    Result event → {"type":"result", "data": {...},   "ts": float}

    data keys: graph_summary, results, llm_explanation, used_llm, elapsed_seconds

    When issue_title/issue_body are provided the LLM prompt switches to
    issue-triage mode with build_issue_llm_context().
    """
    start      = time.perf_counter()
    source_map = {sf.rel_path: sf for sf in source_files}
    gsum       = graph_sum or graph_summary(G)
    is_issue   = issue_title is not None

    mode_label = "issue triage" if is_issue else "question"

    # ── Step 1: keyword + graph ranking ──────────────────────────────────────
    yield _step(
        f"Ranking candidates for {mode_label} by keyword match and "
        "import-graph centrality…",
        start,
    )

    n_fetch    = max(top_n, _LLM_TOP_K)
    candidates = answer_question(question, source_files, G, top_n=n_fetch)

    file_preview = ", ".join(f"`{c.rel_path}`" for c in candidates[:3])
    yield _step(f"Top candidates: {file_preview}…", start)

    # ── Step 2: LLM reasoning ────────────────────────────────────────────────
    client, backend = _make_client()
    used_llm        = False
    llm_explanation = None

    if backend == "none":
        yield _step(
            "No LLM credentials (set ANTHROPIC_API_KEY or QWEN_API_KEY). "
            "Returning keyword/graph results only.",
            start,
        )
    else:
        backend_label = {
            "anthropic": f"Claude ({_ANTHROPIC_MODEL})",
            "qwen":    f"Qwen ({_QWEN_MODEL})",
        }[backend]

        yield _step(
            f"Building grounded {'triage' if is_issue else 'analysis'} prompt "
            f"({_LLM_TOP_K} files, up to {_CONTENT_CHARS} chars each)…",
            start,
        )

        if is_issue:
            prompt = build_issue_llm_context(
                issue_title, issue_body or "", issue_number,
                candidates[:_LLM_TOP_K], source_map, G,
            )
        else:
            prompt = build_llm_context(question, candidates[:_LLM_TOP_K], source_map, G)

        action = "triage issue" if is_issue else "explain relevance"
        yield _step(
            f"Asking {backend_label} to {action} ({len(prompt):,} chars prompt)…",
            start,
        )

        try:
            llm_explanation = _call_llm(client, backend, prompt)
            used_llm = True
            yield _step(
                f"{backend_label} {mode_label} complete "
                f"({len(llm_explanation):,} chars response).",
                start,
            )
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            yield _step(
                f"LLM call failed ({type(exc).__name__}: {exc}). "
                "Falling back to keyword/graph results.",
                start,
            )

    # ── Step 3: emit final result ─────────────────────────────────────────────
    results_payload = [
        {
            "file":        c.rel_path,
            "language":    c.language,
            "score":       round(c.score, 4),
            "explanation": c.explanation,
        }
        for c in candidates[:top_n]
    ]

    yield _ndjson({
        "type": "result",
        "ts":   _ts(start),
        "data": {
            "graph_summary":   gsum,
            "results":         results_payload,
            "llm_explanation": llm_explanation,
            "used_llm":        used_llm,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
        },
    })
