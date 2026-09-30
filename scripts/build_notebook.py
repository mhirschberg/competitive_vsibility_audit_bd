"""Build or verify the self-contained notebook from shared Python sources."""

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from notebook_builder import NOTEBOOK, build_notebook  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Fail if notebook is stale")
    mode.add_argument("--write", action="store_true", help="Update generated cells")
    args = parser.parse_args(argv)

    expected = build_notebook()
    if args.check:
        if NOTEBOOK.read_bytes() != expected:
            print("Notebook is stale; run scripts/build_notebook.py --write", file=sys.stderr)
            return 1
        print("Notebook generated cells are in sync")
        return 0

    if NOTEBOOK.read_bytes() != expected:
        NOTEBOOK.write_bytes(expected)
        print("Updated generated notebook cells")
    else:
        print("Notebook already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
