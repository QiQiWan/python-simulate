from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geoai_simkit.results.runtime_adapter import RuntimeResultStoreAdapter
from geoai_simkit.runtime import CompileConfig, RuntimeCompiler, RuntimeConfig

from .orchestrator import build_runtime


@dataclass(slots=True)
class DistributedBackendResult:
    solved_model: Any
    bundle: Any
    runtime_report: Any
    result_store: Any
    result_db: Any


class DistributedBackend:
    def __init__(self, compiler=None, runtime_factory=None, result_adapter=None):
        self.compiler = compiler or RuntimeCompiler()
        self.runtime_factory = runtime_factory or build_runtime
        self.result_adapter = result_adapter or RuntimeResultStoreAdapter()

    def solve(self, prepared_case, settings, *, compile_config=None, runtime_config=None):
        compile_cfg = compile_config or CompileConfig()
        runtime_cfg = runtime_config or RuntimeConfig(partition_count=compile_cfg.partition_count)
        bundle = self.compiler.compile_case(prepared_case, compile_cfg)
        runtime = self.runtime_factory(runtime_cfg, settings)
        runtime.initialize(bundle)
        try:
            report = runtime.execute()
            result_db = self.result_adapter.from_runtime_store(runtime.result_store)
            return DistributedBackendResult(
                solved_model=runtime.solved_model,
                bundle=bundle,
                runtime_report=report,
                result_store=runtime.result_store,
                result_db=result_db,
            )
        finally:
            runtime.shutdown()
