from __future__ import annotations

from pathlib import Path
import os
import sys


def bootstrap() -> Path:
    here = Path(__file__).resolve().parent
    root = here.parent if here.name == "tools" else here
    src = root / "src"
    tools = root / "tools"
    for path in (src, tools):
        text = str(path)
        if path.exists() and text not in sys.path:
            sys.path.insert(0, text)
    for folder in ("reports", "exports", "logs", "autosave"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GEOAI_SIMKIT_ROOT", str(root))
    return root
