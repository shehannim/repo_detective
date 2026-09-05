"""
graph.py — Build a dependency graph from a list of source files.

Nodes  = source files (identified by their rel_path)
Edges  = import / include / require relationships discovered by
         lightweight regex-based parsing (no AST required).

Language-specific parsers live in the PARSERS dict below.
Each parser returns a list of raw import strings (module names or
relative paths) that are then resolved against the known file set.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, List, Set

import networkx as nx

from .ingestion import SourceFile

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

Parser = Callable[[str, str], List[str]]   # (content, rel_path) → imports

# ---------------------------------------------------------------------------
# Language-specific import parsers (regex-based, intentionally lightweight)
# ---------------------------------------------------------------------------

# Python: import X, from X import Y, from .X import Y
_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+))",
    re.MULTILINE,
)

def _parse_python(content: str, rel_path: str) -> List[str]:
    hits: List[str] = []
    for m in _PY_IMPORT.finditer(content):
        if m.group(1):                         # from X import …
            hits.append(m.group(1).strip())
        else:                                  # import X, Y
            for part in m.group(2).split(","):
                hits.append(part.strip().split(" ")[0])  # handle "import X as Y"
    return hits


# JS/TS: import … from "…", require("…"), export … from "…"
_JS_IMPORT = re.compile(
    r"""(?:import|export)\s+.*?\s+from\s+['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE | re.DOTALL,
)

def _parse_js(content: str, rel_path: str) -> List[str]:
    hits: List[str] = []
    for m in _JS_IMPORT.finditer(content):
        target = m.group(1) or m.group(2)
        if target:
            hits.append(target)
    return hits


# Go: import "pkg" or import ( "pkg1" \n "pkg2" )
_GO_IMPORT = re.compile(r'"([^"]+)"')
_GO_IMPORT_BLOCK = re.compile(r"import\s+(?:\"([^\"]+)\"|(\([^)]+\)))", re.DOTALL)

def _parse_go(content: str, rel_path: str) -> List[str]:
    hits: List[str] = []
    for m in _GO_IMPORT_BLOCK.finditer(content):
        if m.group(1):
            hits.append(m.group(1))
        elif m.group(2):
            for pkg in _GO_IMPORT.findall(m.group(2)):
                hits.append(pkg)
    return hits


# Rust: use crate::X; mod X;
_RUST_USE = re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE)
_RUST_MOD = re.compile(r"^\s*mod\s+(\w+)\s*;", re.MULTILINE)

def _parse_rust(content: str, rel_path: str) -> List[str]:
    hits = [m.group(1) for m in _RUST_USE.finditer(content)]
    hits += [m.group(1) for m in _RUST_MOD.finditer(content)]
    return hits


# Java: import com.example.Foo;
_JAVA_IMPORT = re.compile(r"^\s*import\s+([\w.]+)\s*;", re.MULTILINE)

def _parse_java(content: str, rel_path: str) -> List[str]:
    return [m.group(1) for m in _JAVA_IMPORT.finditer(content)]


# Ruby: require "x", require_relative "x"
_RUBY_REQUIRE = re.compile(r"""require(?:_relative)?\s+['"]([^'"]+)['"]""")

def _parse_ruby(content: str, rel_path: str) -> List[str]:
    return [m.group(1) for m in _RUBY_REQUIRE.finditer(content)]


# C / C++: #include "local.h"  (skip <system> headers)
_C_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.MULTILINE)

def _parse_c(content: str, rel_path: str) -> List[str]:
    return [m.group(1) for m in _C_INCLUDE.finditer(content)]


# PHP: use Foo\Bar; require 'file.php'; include 'file.php'
_PHP_USE = re.compile(r"^\s*use\s+([\w\\]+)", re.MULTILINE)
_PHP_REQUIRE = re.compile(r"""(?:require|include)(?:_once)?\s*\(?['"]([^'"]+)['"]\)?""")

def _parse_php(content: str, rel_path: str) -> List[str]:
    hits = [m.group(1) for m in _PHP_USE.finditer(content)]
    hits += [m.group(1) for m in _PHP_REQUIRE.finditer(content)]
    return hits


PARSERS: Dict[str, Parser] = {
    "Python": _parse_python,
    "JavaScript": _parse_js,
    "TypeScript": _parse_js,
    "Go": _parse_go,
    "Rust": _parse_rust,
    "Java": _parse_java,
    "Kotlin": _parse_java,   # same import syntax
    "Ruby": _parse_ruby,
    "C": _parse_c,
    "C++": _parse_c,
    "PHP": _parse_php,
}

# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------

def _resolve_import(raw: str, source_rel: str, known_rel_paths: Set[str]) -> str | None:
    """
    Try to map a raw import string onto a known rel_path.
    Returns the matching rel_path or None.
    """
    # Relative path imports (starts with . or / or ..)
    if raw.startswith(".") or raw.startswith("/"):
        base_dir = str(Path(source_rel).parent)
        candidate = Path(base_dir) / raw
        # Try exact, then with common extensions
        for ext in ("", ".py", ".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"):
            c = candidate.with_suffix("").as_posix() + ext if ext.startswith(".") else \
                (candidate.as_posix() + ext)
            if c in known_rel_paths:
                return c
        return None

    # Dotted module path → try converting dots to slashes
    # e.g. "src.ingestion" → "src/ingestion.py"
    slash_form = raw.replace(".", "/")
    for ext in ("", ".py", ".js", ".ts", ".go", ".rb", ".rs", ".java", ".php"):
        candidate = slash_form + ext
        if candidate in known_rel_paths:
            return candidate
    # Also try just the last component
    last = raw.split(".")[-1].split("/")[-1]
    for rel in known_rel_paths:
        if Path(rel).stem == last:
            return rel
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_dependency_graph(source_files: List[SourceFile]) -> nx.DiGraph:
    """
    Build a directed dependency graph from *source_files*.

    Node attributes:
      - language (str)
      - lines    (int)   number of lines in the file

    Edge attributes:
      - raw_import (str) the original import string that created the edge
    """
    G: nx.DiGraph = nx.DiGraph()
    known_rel_paths: Set[str] = {sf.rel_path for sf in source_files}

    # Add all nodes first
    for sf in source_files:
        G.add_node(
            sf.rel_path,
            language=sf.language,
            lines=sf.content.count("\n") + 1,
        )

    # Add edges
    for sf in source_files:
        parser = PARSERS.get(sf.language)
        if parser is None:
            continue
        raw_imports = parser(sf.content, sf.rel_path)
        for raw in raw_imports:
            target = _resolve_import(raw, sf.rel_path, known_rel_paths)
            if target and target != sf.rel_path:
                G.add_edge(sf.rel_path, target, raw_import=raw)

    return G


def graph_summary(G: nx.DiGraph) -> dict:
    """Return a brief summary of the graph for logging / API responses."""
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "languages": list({G.nodes[n].get("language", "?") for n in G.nodes}),
        "top_imported": [
            n for n, d in sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:10]
        ],
    }
