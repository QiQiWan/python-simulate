from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    project_name: str = "geoai-simkit"
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".geoai_simkit")
    default_export_dir: Path = field(default_factory=lambda: Path.cwd() / "exports")
    preview_theme: str = "document"
