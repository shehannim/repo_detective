# repo-detective 🔍

> Analyse any **public GitHub repository** and answer natural-language questions about its structure — no LLM API key required.

## Features

| Feature | Details |
|---|---|
| **Repo ingestion** | Clones at `depth=1` via GitPython; skips `.git`, `node_modules`, build artifacts, binaries |
| **Language detection** | 25+ languages identified by file extension |
| **Dependency graph** | Directed `networkx.DiGraph`; edges from regex-parsed imports/requires/includes |
| **NL search** | Keyword TF scoring + PageRank + in-degree centrality — no external API needed |
| **Caching** | In-process LRU cache (5 repos, 1 h TTL) — repeated questions are instant |
| **REST API** | FastAPI + Pydantic v2, auto-generated OpenAPI docs at `/docs` |

## Project structure

```
repo-detective/
├── src/
│   ├── __init__.py      # package marker
│   ├── main.py          # FastAPI app  (endpoints: /ask, /health, /cache)
│   ├── ingestion.py     # clone repo, walk files, detect language
│   ├── graph.py         # build networkx dependency graph
│   ├── search.py        # score & rank files for a NL question
│   └── cache.py         # in-process LRU cache
├── requirements.txt
└── README.md
```

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server (reload optional for dev)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Ask a question (replace URL and question as needed)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/tiangolo/fastapi",
    "question": "Where is authentication handled?",
    "top_n": 5
  }'
```

## API reference

### `POST /ask`

| Field | Type | Default | Description |
|---|---|---|---|
| `repo_url` | `string` | required | Public Git clone URL |
| `question` | `string` | required | Natural-language question |
| `top_n` | `int` | `5` | Number of files to return (1–20) |
| `refresh` | `bool` | `false` | Force re-clone (bypass cache) |

**Response**

```json
{
  "repo_url": "...",
  "question": "...",
  "graph_summary": {
    "nodes": 42,
    "edges": 87,
    "languages": ["Python", "YAML"],
    "top_imported": ["src/utils.py", "src/models.py"]
  },
  "results": [
    {
      "file": "src/auth.py",
      "language": "Python",
      "score": 14.72,
      "explanation": "File path matches keyword(s): auth. Imported/referenced by 3 other file(s). ..."
    }
  ],
  "cached": false,
  "elapsed_seconds": 8.42
}
```

### `GET /health`

Returns `{ "status": "ok", "version": "0.1.0" }`.

### `GET /cache`

Returns current LRU cache statistics.

### Interactive docs

Visit **http://localhost:8000/docs** for the auto-generated Swagger UI.

## How scoring works

Each file receives a combined score:

```
score = keyword_tf_score
      + path_keyword_bonus   (3× per keyword hit in the path)
      + pagerank × 50        (global importance in the import graph)
      + log1p(in_degree) × 5 (how many files import this one)
```

## Supported languages for dependency edges

Python · JavaScript · TypeScript · Go · Rust · Java · Kotlin · Ruby · C · C++ · PHP

(All other languages are still indexed and scored by keyword.)
