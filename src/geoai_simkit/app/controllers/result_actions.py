from __future__ import annotations

"""GUI-facing result/postprocessing action controller."""

from dataclasses import dataclass
from typing import Any

from geoai_simkit.adapters import as_project_context
from geoai_simkit.contracts import project_result_store_summary
from geoai_simkit.modules import postprocessing


@dataclass(slots=True)
class ResultActionController:
    project: Any

    def context(self):
        return as_project_context(self.project)

    def summary(self) -> dict[str, Any]:
        return project_result_store_summary(self.context()).to_dict()

    def summarize(self, *, processor: str = "auto"):
        return postprocessing.summarize_results(self.context(), processor=processor)

    def project_payload(self) -> dict[str, Any]:
        return postprocessing.build_project_result_summary(self.context())


__all__ = ["ResultActionController"]
