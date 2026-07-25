"""Export the FastAPI contract used for TypeScript client generation."""

from __future__ import annotations

import json
from pathlib import Path

from werewolf_agent.api.bootstrap import create_app


def main() -> None:
    """Write deterministic OpenAPI JSON at the repository root."""
    target = Path(__file__).resolve().parents[1] / "openapi.json"
    target.write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
