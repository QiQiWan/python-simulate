from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from geoai_simkit.pipeline import AnalysisCaseSpec, build_preprocessor_snapshot


@dataclass(slots=True)
class PreprocessOverview:
    case_name: str
    n_region_surfaces: int
    n_region_adjacencies: int
    n_boundary_adjacencies: int
    n_interface_candidates: int
    n_node_split_plans: int
    n_interface_elements: int
    metadata: dict[str, Any] = field(default_factory=dict)


class PreprocessService:
    def build_overview(self, case: AnalysisCaseSpec) -> PreprocessOverview:
        artifact = build_preprocessor_snapshot(case)
        snapshot = artifact.snapshot
        payload = snapshot.to_dict()
        return PreprocessOverview(
            case_name=case.name,
            n_region_surfaces=len(payload.get('region_surfaces') or ()),
            n_region_adjacencies=len(payload.get('region_adjacencies') or ()),
            n_boundary_adjacencies=len(payload.get('boundary_adjacencies') or ()),
            n_interface_candidates=len(payload.get('interface_candidates') or ()),
            n_node_split_plans=len(payload.get('node_split_plans') or ()),
            n_interface_elements=len(payload.get('interface_element_definitions') or ()),
            metadata=dict(payload.get('metadata') or {}),
        )


__all__ = ['PreprocessOverview', 'PreprocessService']
