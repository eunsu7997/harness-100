"""Launcher usable with `python -I -B harness100_cli.py ...` from any working directory.

-I keeps the current directory and PYTHONPATH off sys.path, so a `harness100/` folder inside an
untrusted project cannot shadow this package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness100.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
