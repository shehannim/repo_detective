"""
Root entrypoint shim for deployment platforms (Render, Railway, etc.)
that execute `uvicorn src.main:app`.
"""
import sys
import pathlib

# Ensure backend directory is in sys.path
_backend_dir = str(pathlib.Path(__file__).parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Import app from backend.src.main
from backend.src.main import app  # noqa: F401
