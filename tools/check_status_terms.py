from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("production", "commercial", "fully resident", "fully_resident")
EXEMPT_PARTS = {"docs/archive", "tests", "research/status_terms.py", "benchmark_report.py"}


def is_exempt(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(part in rel for part in EXEMPT_PARTS)


def main() -> int:
    hits = []
    for base in (ROOT / "src", ROOT / "docs", ROOT / "README.md"):
        paths = [base] if base.is_file() else list(base.rglob("*.py")) + list(base.rglob("*.md"))
        for path in paths:
            if not path.exists() or is_exempt(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for term in BANNED:
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", text):
                    hits.append(f"{path.relative_to(ROOT)}: {term}")
    if hits:
        print("Status-term cleanup warnings:")
        print("\n".join(hits))
    else:
        print("No user-facing banned status terms found outside compatibility/archives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
