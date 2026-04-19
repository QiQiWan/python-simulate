from ._version import __version__
from .config import AppConfig

try:
    from .core.model import SimulationModel
except Exception:
    SimulationModel = None  # type: ignore

try:
    from .pipeline import AnalysisCaseBuilder, AnalysisCaseSpec, GeneralFEMSolver
except Exception:
    AnalysisCaseBuilder = None  # type: ignore
    AnalysisCaseSpec = None  # type: ignore
    GeneralFEMSolver = None  # type: ignore

try:
    from .runtime import CompileConfig, RuntimeCompiler, RuntimeConfig
except Exception:
    CompileConfig = None  # type: ignore
    RuntimeCompiler = None  # type: ignore
    RuntimeConfig = None  # type: ignore

__all__ = ['AppConfig', 'SimulationModel', 'AnalysisCaseBuilder', 'AnalysisCaseSpec', 'CompileConfig', 'GeneralFEMSolver', 'RuntimeCompiler', 'RuntimeConfig', '__version__']
