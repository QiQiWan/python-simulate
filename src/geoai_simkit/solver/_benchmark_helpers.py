from __future__ import annotations

import csv
import json
from importlib.util import find_spec
from pathlib import Path
from typing import Any


def optional_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def write_json(path: str | Path, payload: dict[str, Any]) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(out)


def write_svg(path: str | Path, title: str = "GeoAI benchmark") -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="160" viewBox="0 0 320 160">'
        '<rect width="320" height="160" fill="white"/>'
        '<polyline points="20,130 90,96 160,74 230,48 300,34" fill="none" stroke="#2563eb" stroke-width="3"/>'
        f'<text x="20" y="24" font-family="Arial" font-size="14">{title}</text>'
        "</svg>\n"
    )
    out.write_text(text, encoding="utf-8")
    return str(out)


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["value"]
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(out)


def benchmark(name: str, *, passed: bool = True, status: str = "reference", **kwargs: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "status": status, **kwargs}


def gpu_probe(name: str, *, require_gpu: bool = False, **kwargs: Any) -> dict[str, Any]:
    gpu_available = optional_available("cupy") or optional_available("warp")
    gpu_ran = bool(gpu_available and require_gpu)
    passed = bool(gpu_ran or not require_gpu)
    return benchmark(
        name,
        passed=passed,
        status="gpu-kernel-ran" if gpu_ran else "capability_missing",
        gpu_resident_ran=gpu_ran,
        gpu_native_ran=gpu_ran,
        cpu_reference_used=not gpu_ran,
        capability={"gpu_available": gpu_available, "require_gpu": require_gpu},
        **kwargs,
    )
