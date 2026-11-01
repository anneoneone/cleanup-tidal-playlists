"""Write the API contract to frontend/openapi.json (the UI types come from it)."""

import json
import os
import sys
import tempfile
from pathlib import Path

from cratekeeper.api.app import create_app
from cratekeeper.app import App
from cratekeeper.home import Home


def main() -> None:
    """Export the OpenAPI schema without touching the real Cratekeeper home."""
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("frontend/openapi.json")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["CRATEKEEPER_HOME"] = tmp
        core = App.open(Home(root=Path(tmp)))
        spec = create_app(core, 8765).openapi()
        core.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
