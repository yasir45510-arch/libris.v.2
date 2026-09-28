"""Launch LIBRIS with its project virtual environment when available."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def use_project_environment() -> None:
    """Restart under .venv so PDF/EPUB dependencies are always available."""
    current = Path(sys.executable).resolve()
    if (
        VENV_PYTHON.exists()
        and current != VENV_PYTHON.resolve()
        and os.environ.get("LIBRIS_USING_VENV") != "1"
    ):
        environment = os.environ.copy()
        environment["LIBRIS_USING_VENV"] = "1"
        subprocess.Popen(
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=PROJECT_ROOT,
            env=environment,
        )
        raise SystemExit(0)


def main() -> None:
    use_project_environment()
    from ui.app import run

    run()


if __name__ == "__main__":
    main()
