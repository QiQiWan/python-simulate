from __future__ import annotations

"""Runtime compiler adapters."""

from geoai_simkit.contracts import PluginCapability, PluginHealth, RuntimeBundlePayload, RuntimeCompileRequest


class DefaultRuntimeCompilerBackend:
    key = "default_runtime_compiler"
    label = "Default runtime bundle compiler"
    capabilities = PluginCapability(
        key=key,
        label=label,
        category="runtime_compiler",
        version="1",
        features=("runtime_bundle", "manifest", "compile_report"),
        supported_inputs=("PreparedCase",),
        supported_outputs=("RuntimeBundlePayload",),
        health=PluginHealth(available=True),
    )

    def compile(self, request: RuntimeCompileRequest) -> RuntimeBundlePayload:
        from geoai_simkit.runtime import RuntimeCompiler

        bundle = RuntimeCompiler().compile_case(request.prepared_case, request.compile_config)
        compile_report = bundle.compile_report.to_dict() if hasattr(bundle.compile_report, "to_dict") else {}
        return RuntimeBundlePayload(
            bundle=bundle,
            manifest=dict(getattr(bundle, "manifest", {}) or {}),
            compile_report=compile_report,
            metadata={"backend": self.key, **dict(request.metadata)},
        )


__all__ = ["DefaultRuntimeCompilerBackend"]
