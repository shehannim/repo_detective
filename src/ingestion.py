"""
ingestion.py — Clone or fetch a public GitHub repository,
walk its file tree, and return only source-code files (by extension),
skipping build artifacts, VCS internals, and other noise.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, NamedTuple

import git  # GitPython

# ---------------------------------------------------------------------------
# Language detection by extension
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyw": "Python",
    # JavaScript / TypeScript
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    # Web
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    # Ruby
    ".rb": "Ruby",
    ".rake": "Ruby",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # Java / Kotlin / Scala
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".scala": "Scala",
    # C / C++
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    # C#
    ".cs": "C#",
    # PHP
    ".php": "PHP",
    # Swift
    ".swift": "Swift",
    # Shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    # Configuration / data (still useful for structure)
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "INI",
    ".env": "ENV",
    # Documentation
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
    # SQL
    ".sql": "SQL",
    # Dockerfile
    "Dockerfile": "Dockerfile",
    ".dockerfile": "Dockerfile",
}

# ---------------------------------------------------------------------------
# Directories / path segments to skip entirely
# ---------------------------------------------------------------------------

SKIP_DIRS: set[str] = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",          # Rust / Maven
    "out",
    ".next",
    ".nuxt",
    ".venv",
    "venv",
    "env",
    ".env",
    "virtualenv",
    "vendor",          # Go / PHP
    "third_party",
    "Pods",            # iOS
    ".gradle",
    ".idea",
    ".vscode",
    "__generated__",
    "generated",
    "coverage",
    ".nyc_output",
    "storybook-static",
}

# ---------------------------------------------------------------------------
# File-level patterns to skip (glob-style names)
# ---------------------------------------------------------------------------

SKIP_FILE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\.min\.(js|css)$"),
    re.compile(r"\.map$"),
    re.compile(r"\.lock$"),
    re.compile(r"package-lock\.json$"),
    re.compile(r"yarn\.lock$"),
    re.compile(r"poetry\.lock$"),
    re.compile(r"Pipfile\.lock$"),
    re.compile(r".*\.(pyc|pyo|class|o|obj|dll|so|dylib|exe|bin|wasm)$"),
    re.compile(r".*\.(png|jpg|jpeg|gif|ico|svg|webp|bmp|tiff)$"),
    re.compile(r".*\.(mp4|mp3|wav|avi|mov|mkv)$"),
    re.compile(r".*\.(zip|tar|gz|bz2|rar|7z)$"),
    re.compile(r".*\.(pdf|docx?|xlsx?|pptx?)$"),
    re.compile(r".*\.(ttf|woff2?|eot)$"),
]


class SourceFile(NamedTuple):
    """Represents a single source file in the repository."""
    path: Path          # absolute path on disk
    rel_path: str       # path relative to repo root
    language: str       # detected language
    content: str        # UTF-8 text content


def _detect_language(path: Path) -> str | None:
    """Return the language for *path*, or None if it should be skipped."""
    name = path.name
    # Special full-filename match (e.g. "Dockerfile")
    if name in EXTENSION_TO_LANGUAGE:
        return EXTENSION_TO_LANGUAGE[name]
    suffix = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)


def _should_skip_file(path: Path) -> bool:
    name = path.name
    for pattern in SKIP_FILE_PATTERNS:
        if pattern.search(name):
            return True
    return False


def _walk_repo(root: Path) -> List[SourceFile]:
    """Recursively walk *root* and return all recognised source files."""
    source_files: List[SourceFile] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip-dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            abs_path = Path(dirpath) / filename
            if _should_skip_file(abs_path):
                continue
            language = _detect_language(abs_path)
            if language is None:
                continue
            rel = abs_path.relative_to(root).as_posix()
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            source_files.append(SourceFile(abs_path, rel, language, content))

    return source_files


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_repo(repo_url: str, target_dir: str | None = None) -> tuple[Path, List[SourceFile]]:
    """
    Clone *repo_url* into *target_dir* (or a temp dir) and return
    (repo_root, list_of_source_files).

    The caller is responsible for cleaning up *target_dir* when done.
    If *target_dir* is None a temporary directory is created whose path
    is returned so the caller can remove it later.
    """
    if target_dir is None:
        target_dir = tempfile.mkdtemp(prefix="repo_detective_")

    repo_root = Path(target_dir)

    # Clone with depth=1 to keep things fast
    git.Repo.clone_from(
        repo_url,
        str(repo_root),
        depth=1,
        no_single_branch=True,
    )

    source_files = _walk_repo(repo_root)
    return repo_root, source_files


def cleanup_repo(repo_root: Path) -> None:
    """Remove the cloned repository from disk."""
    shutil.rmtree(str(repo_root), ignore_errors=True)
