from .config import AppConfig

try:  # pragma: no cover - optional heavy deps like pyvista may be absent in headless envs
    from .core.model import SimulationModel
except Exception:  # pragma: no cover
    SimulationModel = None  # type: ignore

__all__ = ["AppConfig", "SimulationModel"]

__version__ = "0.1.42"
