"""Entry point.

    python main.py                 # auto-switches to .venv's Python if needed
    uvicorn main:app --reload      # with the venv activated
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _running_in_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def _relaunch_in_venv() -> None:
    """Re-run this script with the project's .venv interpreter if we aren't already in it."""
    if _running_in_venv():
        return
    py = _venv_python()
    if not py.exists():
        sys.exit(
            f"Virtual environment not found at {VENV_DIR}.\n"
            f"Create it with:  python -m venv .venv  &&  "
            f"{py} -m pip install -r requirements.txt"
        )
    try:
        code = subprocess.call([str(py), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT)
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    _relaunch_in_venv()

    import uvicorn

    os.chdir(ROOT)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
else:
    from app.main import app  # noqa: F401  (re-exported for `uvicorn main:app`)
