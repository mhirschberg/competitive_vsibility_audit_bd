"""Keep the standalone Colab notebook's research race in sync with its source."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "competitive_visibility_audit_bd.ipynb"
SOURCE = ROOT / "research_fallback.py"
CELL_ID = "research-provider-race"


def main():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"cellView": "form", "id": CELL_ID},
        "outputs": [],
        "source": [
            "#@title 3E. Load resilient research providers\n",
            "#@markdown Race ChatGPT and Gemini for internal research; keep Google AI Mode measured separately.\n",
            "\n",
            *source.splitlines(keepends=True),
        ],
    }
    cells = notebook["cells"]
    existing = next(
        (i for i, item in enumerate(cells) if item.get("metadata", {}).get("id") == CELL_ID),
        None,
    )
    if existing is None:
        run_index = next(
            i for i, item in enumerate(cells)
            if item.get("metadata", {}).get("id") == "final-run"
        )
        cells.insert(run_index, cell)
    else:
        cells[existing] = cell
    NOTEBOOK.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
