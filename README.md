# repo-detective 🔍

> Real-time repository intelligence and architectural reasoning engine with an interactive web interface.

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
├── backend/                  # Isolated Python FastAPI service (Secure)
│   ├── src/
│   │   ├── main.py           # Endpoints: /ask, /ask/stream, /issue, /issue/stream
│   │   ├── ingestion.py      # Git cloning, AST file walking, lang detection
│   │   ├── graph.py          # NetworkX dependency digraph builder
│   │   ├── search.py         # Keyword TF-IDF + PageRank + centrality scoring
│   │   ├── cache.py          # LRU repo graph cache
│   │   ├── github.py         # GitHub API issue fetching & triage query synth
│   │   └── qa_engine.py      # Grounded LLM reasoning & NDJSON streaming
│   ├── requirements.txt
│   ├── Procfile
│   ├── railway.json
│   └── .env.example
├── frontend/                 # Decoupled React (Vite) client application
│   ├── src/
│   │   ├── components/       # Modular UI components (Navbar, Hero, Panels...)
│   │   ├── App.jsx           # State coordination & NDJSON streaming reader
│   │   ├── index.css         # Dark purple glow modern aesthetic
│   │   └── main.jsx          # React 18 root
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
├── Procfile
├── railway.json
└── README.md
```

## Quick start

### 1. Run the Backend (Python / FastAPI)
```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Run the Frontend (React / Vite)
```bash
cd frontend
npm install
npm run dev
# Running on http://localhost:5173
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
