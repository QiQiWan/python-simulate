from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from geoai_simkit.core.model import SimulationModel


@dataclass(slots=True)
class AuditFinding:
    severity: str
    category: str
    message: str
    remedy: str = ''


@dataclass(slots=True)
class AuditReport:
    findings: list[AuditFinding]

    @property
    def summary(self) -> str:
        if not self.findings:
            return 'No obvious layout or performance bottlenecks were detected.'
        return f'{len(self.findings)} issue(s): ' + '; '.join(item.message for item in self.findings[:4])


def analyze_ui_and_model_performance(model: SimulationModel | None) -> AuditReport:
    findings: list[AuditFinding] = []
    if model is None:
        return AuditReport(findings)
    state = model.geometry_state() if hasattr(model, 'geometry_state') else str(model.metadata.get('geometry_state') or 'geometry')
    if state != 'meshed':
        findings.append(AuditFinding('info', 'workflow', 'The current model is geometry-only; volume mesh checks and solve previews should stay deferred.', 'Keep IFC / CAD import lightweight and trigger meshing explicitly from the mesh engine panel.'))
    obj_count = len(model.object_records)
    if obj_count > 120:
        findings.append(AuditFinding('warning', 'layout', f'The scene tree currently contains {obj_count} objects, which can make full tree refreshes expensive.', 'Prefer lazy refresh / filtered views and avoid rebuilding all rows after every small edit.'))
    if obj_count > 300:
        findings.append(AuditFinding('warning', 'viewer', 'High object count suggests the viewer should default to fast preview mode (no edge overlay, no auto-fit after every update).', 'Disable edge rendering until the model is meshed or the user explicitly enables detailed preview.'))
    if model.has_volume_mesh() and len(model.region_tags) > 80:
        findings.append(AuditFinding('warning', 'meshing', f'The model exposes {len(model.region_tags)} regions; material/region tables may become hard to read.', 'Add search/filter widgets and batch assignment actions for materials and stage activation.'))
    if not model.materials and obj_count:
        findings.append(AuditFinding('warning', 'workflow', 'No material assignments were found for the imported geometry.', 'Associate materials before meshing so the mesh engine can refine the important regions first.'))
    return AuditReport(findings)
