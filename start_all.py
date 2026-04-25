"""Single-command launcher for the full ParkVision system.

What this starts (in one process):
- FastAPI backend on http://127.0.0.1:8000
- Embedded YOLO vision workers for every ``is_live`` lot (MJPEG + occupancy)

Usage::

    python start_all.py            # auto-uses ./venv if present
    python start_all.py --open     # also open the dashboard in the browser

Override defaults via env, e.g.::

    PARKING_VISION_OCCUPANCY_MODE=overlap python start_all.py
    PARKVISION_DEBUG_LOOP=1 python start_all.py
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _venv_python() -> Path | None:
    candidates = [
        ROOT / "venv" / "Scripts" / "python.exe",  # Windows
        ROOT / "venv" / "bin" / "python",           # POSIX
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _reexec_in_venv(venv_py: Path) -> None:
    """Restart this script under the project's venv interpreter."""
    if Path(sys.executable).resolve() == venv_py.resolve():
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the full ParkVision system.")
    parser.add_argument("--open", action="store_true", help="Open the dashboard in your browser once the server is up.")
    parser.add_argument("--no-venv", action="store_true", help="Don't re-exec under ./venv; use the current interpreter.")
    args = parser.parse_args()

    venv_py = None if args.no_venv else _venv_python()
    if venv_py is not None:
        _reexec_in_venv(venv_py)

    os.environ.setdefault("PARKING_VISION_OCCUPANCY_MODE", "point")

    try:
        from backend.config import HOST, PORT, DEBUG
        import uvicorn
    except ImportError as e:
        print(f"ERROR: backend dependencies not importable: {e}", file=sys.stderr)
        print("Install requirements first:  pip install -r requirements.txt -r requirements-ai.txt", file=sys.stderr)
        sys.exit(1)

    base_url = f"http://{HOST}:{PORT}"
    bar = "=" * 64
    print(bar)
    print(" ParkVision — full system")
    print(bar)
    print(f" Python:           {sys.executable}")
    print(f" Occupancy mode:   {os.environ['PARKING_VISION_OCCUPANCY_MODE']}")
    print(f" Reload (DEBUG):   {DEBUG}")
    print()
    print(" Endpoints:")
    print(f"   Dashboard:      {base_url}/")
    print(f"   API docs:       {base_url}/docs")
    print(f"   Slot stream:    {base_url}/api/slots/stream  (SSE)")
    print(f"   Live MJPEG:     {base_url}/api/stream/mjpeg/{{lot_id}}")
    print()
    print(" Press Ctrl+C to stop.")
    print(bar)

    if args.open:
        try:
            webbrowser.open(base_url + "/")
        except Exception:
            pass

    uvicorn.run(
        "backend.app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        reload_excludes=[".venv", "venv", "*.pyc", "video", "models", "database"],
        log_level="info",
    )


if __name__ == "__main__":
    main()
