from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(slots=True)
class RegionBoundarySurfaceSummary: region_name: str=''; face_count: int=0; metadata: dict[str, Any]=field(default_factory=dict)
@dataclass(slots=True)
class RegionSurfaceInterfaceCandidate: master: str=''; slave: str=''; shared_face_count: int=0; metadata: dict[str, Any]=field(default_factory=dict)
def compute_region_boundary_surfaces(model): return [RegionBoundarySurfaceSummary(n,1) for n in getattr(model,'list_region_names',lambda:[])()]
def compute_region_surface_interface_candidates(model, min_shared_faces=1): return []
def region_surface_summary_rows(items): return [i.__dict__ for i in list(items or [])]
def interface_candidate_summary_rows(items): return [i.__dict__ for i in list(items or [])]
