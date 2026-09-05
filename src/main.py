"""
main.py — FastAPI application for repo-detective.

Endpoints:
  POST /ask           — Answer a free-form question about a repo (JSON)
  POST /ask/stream    — Same, streaming NDJSON
  POST /issue         — Triage a GitHub issue: return most likely relevant files (JSON)
  POST /issue/stream  — Same, streaming NDJSON
  GET  /cache         — Cache stats
  GET  /health        — Health check
"""

from __future__ import annotations

# Load .env if present (dev convenience). On Railway/Render env vars are injected
# directly into the process — dotenv's override=False means those take priority.
import pathlib as _pathlib
from dotenv import load_dotenv as _load_dotenv
for _f in (".env", ".env.example"):
    _p = _pathlib.Path(__file__).parent.parent / _f
    if _p.exists():
        _load_dotenv(_p, override=False)
        break


import json
import tempfile
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from .cache import CacheEntry, repo_cache
from .github import GitHubIssue, fetch_issue, issue_to_question
from .graph import build_dependency_graph, graph_summary
from .ingestion import ingest_repo
from .qa_engine import stream_answer
from .search import SearchResult, answer_question

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    repo_url: str
    question: str
    top_n: int = 5
    refresh: bool = False  # set True to bypass cache

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://") or v.startswith("git@")):
            raise ValueError("repo_url must be a valid Git URL (https:// or git@)")
        return v

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        return v

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int) -> int:
        if not (1 <= v <= 20):
            raise ValueError("top_n must be between 1 and 20")
        return v


class FileResult(BaseModel):
    file: str
    language: str
    score: float
    explanation: str


class AskResponse(BaseModel):
    repo_url: str
    question: str
    graph_summary: dict
    results: List[FileResult]
    llm_explanation: Optional[str] = None  # populated when LLM path runs
    used_llm: bool = False
    cached: bool
    elapsed_seconds: float


class HealthResponse(BaseModel):
    status: str
    version: str


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # nothing to tear down — temp dirs cleaned on cache eviction


app = FastAPI(
    title="repo-detective",
    description=(
        "Analyse any public GitHub repository and answer natural-language "
        "questions about its structure. Optionally uses an LLM for grounded "
        "reasoning when QWEN_API_KEY is set."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared ingestion helper
# ---------------------------------------------------------------------------


async def _ensure_repo(req: AskRequest):
    """
    Return (source_files, G, repo_cached).
    Clones on cache miss; updates the cache on fresh ingest.
    """
    if not req.refresh:
        entry = repo_cache.get(req.repo_url)
        if entry is not None:
            return entry.source_files, entry.graph, True

    tmp_dir = tempfile.mkdtemp(prefix="repo_detective_")
    try:
        _, source_files = ingest_repo(req.repo_url, target_dir=tmp_dir)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to clone repository: {exc}")

    if not source_files:
        raise HTTPException(
            status_code=422,
            detail="No recognised source files found in this repository.",
        )

    G = build_dependency_graph(source_files)
    repo_cache.put(
        req.repo_url,
        CacheEntry(
            source_files=source_files,
            graph=G,
            repo_root=tmp_dir,
            ingested_at=time.time(),
        ),
    )
    return source_files, G, False


from fastapi.responses import FileResponse

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def serve_ui():
    index_path = _pathlib.Path(__file__).parent.parent / "static" / "index.html"
    return FileResponse(
        index_path,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    return HealthResponse(status="ok", version="0.2.0")


@app.get("/cache", tags=["meta"])
async def cache_stats():
    return repo_cache.stats()


# ── Non-streaming /ask (backward-compatible) ─────────────────────────────


@app.post("/ask", response_model=AskResponse, tags=["detective"])
async def ask(req: AskRequest):
    """
    Analyse a repo and answer a question.
    Uses the LLM when QWEN_API_KEY is set in the environment;
    falls back gracefully to keyword/graph ranking otherwise.
    Returns a single JSON object (not streamed).
    """
    t0 = time.perf_counter()
    source_files, G, repo_cached = await _ensure_repo(req)
    gsum = graph_summary(G)

    # Collect the streaming events and pick out the final result
    used_llm = False
    llm_explanation = None
    results_payload = []

    async for line in stream_answer(req.question, source_files, G, top_n=req.top_n, graph_sum=gsum):
        event = json.loads(line)
        if event["type"] == "result":
            data = event["data"]
            used_llm = data["used_llm"]
            llm_explanation = data.get("llm_explanation")
            results_payload = data["results"]

    return AskResponse(
        repo_url=req.repo_url,
        question=req.question,
        graph_summary=gsum,
        results=[FileResult(**r) for r in results_payload],
        llm_explanation=llm_explanation,
        used_llm=used_llm,
        cached=repo_cached,
        elapsed_seconds=round(time.perf_counter() - t0, 3),
    )


# ── Streaming /ask/stream ────────────────────────────────────────────────


@app.post("/ask/stream", tags=["detective"])
async def ask_stream(req: AskRequest):
    """
    Same as /ask but streams NDJSON lines to the client in real time.

    Each line is one of:
      {"type":"step",   "message":"...", "ts": <seconds>}
      {"type":"result", "data": {...},   "ts": <seconds>}
      {"type":"error",  "message":"...", "ts": <seconds>}

    The final "result" line contains the full AskResponse payload plus
    `used_llm` and `llm_explanation`.
    """
    source_files, G, repo_cached = await _ensure_repo(req)
    gsum = graph_summary(G)

    async def _generator() -> AsyncGenerator[str, None]:
        # Prepend a step announcing whether this is a cache hit
        status = "Cache hit" if repo_cached else "Repository cloned"
        yield json.dumps({"type": "step", "message": f"{status}: {req.repo_url}", "ts": 0.0}) + "\n"

        async for line in stream_answer(req.question, source_files, G, top_n=req.top_n, graph_sum=gsum):
            event = json.loads(line)
            # Inject repo metadata into the final result
            if event["type"] == "result":
                event["data"]["repo_url"] = req.repo_url
                event["data"]["question"] = req.question
                event["data"]["graph_summary"] = gsum
                event["data"]["cached"] = repo_cached
                line = json.dumps(event) + "\n"
            yield line

    return StreamingResponse(
        _generator(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )


# ---------------------------------------------------------------------------
# Issue routes
# ---------------------------------------------------------------------------

class IssueRequest(BaseModel):
    repo_url: str
    issue_number: int
    top_n: int = 5
    refresh: bool = False

    @field_validator("repo_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://") or v.startswith("git@")):
            raise ValueError("repo_url must be a valid Git URL")
        return v


class IssueResponse(BaseModel):
    repo_url: str
    issue_number: int
    issue_title: str
    graph_summary: dict
    results: List[FileResult]
    llm_explanation: Optional[str] = None
    used_llm: bool = False
    cached: bool
    elapsed_seconds: float


async def _ensure_repo_by_url(repo_url: str, refresh: bool):
    req = AskRequest(repo_url=repo_url, question="dummy", refresh=refresh)
    return await _ensure_repo(req)


@app.post("/issue", response_model=IssueResponse, tags=["detective"])
async def triage_issue(req: IssueRequest):
    """
    Fetch a GitHub issue and return the most likely relevant files.
    Non-streaming.
    """
    t0 = time.perf_counter()
    try:
        issue = fetch_issue(req.repo_url, req.issue_number)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch issue: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    question = issue_to_question(issue)
    source_files, G, repo_cached = await _ensure_repo_by_url(issue.repo_url, req.refresh)
    gsum = graph_summary(G)

    used_llm = False
    llm_explanation = None
    results_payload = []

    async for line in stream_answer(
        question, source_files, G, top_n=req.top_n, graph_sum=gsum,
        issue_title=issue.title, issue_body=issue.body, issue_number=issue.number
    ):
        event = json.loads(line)
        if event["type"] == "result":
            data = event["data"]
            used_llm = data["used_llm"]
            llm_explanation = data.get("llm_explanation")
            results_payload = data["results"]

    return IssueResponse(
        repo_url=issue.repo_url,
        issue_number=issue.number,
        issue_title=issue.title,
        graph_summary=gsum,
        results=[FileResult(**r) for r in results_payload],
        llm_explanation=llm_explanation,
        used_llm=used_llm,
        cached=repo_cached,
        elapsed_seconds=round(time.perf_counter() - t0, 3),
    )


@app.post("/issue/stream", tags=["detective"])
async def triage_issue_stream(req: IssueRequest):
    """
    Same as /issue but streams NDJSON reasoning steps.
    """
    try:
        issue = fetch_issue(req.repo_url, req.issue_number)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to fetch issue: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    question = issue_to_question(issue)
    source_files, G, repo_cached = await _ensure_repo_by_url(issue.repo_url, req.refresh)
    gsum = graph_summary(G)

    async def _generator() -> AsyncGenerator[str, None]:
        status = "Cache hit" if repo_cached else "Repository cloned"
        yield json.dumps({"type": "step", "message": f"{status}: {issue.repo_url}", "ts": 0.0}) + "\n"

        async for line in stream_answer(
            question, source_files, G, top_n=req.top_n, graph_sum=gsum,
            issue_title=issue.title, issue_body=issue.body, issue_number=issue.number
        ):
            event = json.loads(line)
            if event["type"] == "result":
                event["data"]["repo_url"] = issue.repo_url
                event["data"]["issue_number"] = issue.number
                event["data"]["issue_title"] = issue.title
                event["data"]["graph_summary"] = gsum
                event["data"]["cached"] = repo_cached
                line = json.dumps(event) + "\n"
            yield line

    return StreamingResponse(
        _generator(),
        media_type="application/x-ndjson",
        headers={"X-Content-Type-Options": "nosniff"},
    )
