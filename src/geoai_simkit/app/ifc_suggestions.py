from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from geoai_simkit.core.model import GeometryObjectRecord, MaterialDefinition, SimulationModel


@dataclass(slots=True)
class ObjectSuggestion:
    object_key: str
    role: str
    region_name: str | None
    material_definition: str | None
    reason: str = ''


def suggest_role(record: GeometryObjectRecord) -> tuple[str, str]:
    typ = (record.object_type or '').lower()
    name = (record.name or '').lower()
    parent = (record.parent or '').lower()
    material_names = [str(m).lower() for m in record.metadata.get('material_names', [])]
    if 'ifcwall' in typ or 'wall' in typ:
        return 'wall', 'IFC type indicates wall-like structural element'
    if 'ifcslab' in typ or 'slab' in typ or 'deck' in name:
        return 'slab', 'IFC type indicates slab element'
    if 'ifcbeam' in typ or 'beam' in typ or 'strut' in name:
        return 'beam', 'IFC type/name indicates beam or strut element'
    if 'ifccolumn' in typ or 'column' in typ or 'pile' in name:
        return 'column', 'IFC type/name indicates column or pile'
    if 'open' in name or 'void' in name or 'opening' in typ:
        return 'opening', 'Object likely represents opening/void'
    if 'excavat' in name or 'soil' in name or 'ground' in name or 'terrain' in typ:
        return 'soil', 'Name/type indicates soil/terrain domain'
    if 'proxy' in typ:
        if any(t in name for t in ('support', 'strut', 'brace', 'anchor')):
            return 'support', 'Proxy name suggests support element'
        if any(t in parent for t in ('excavat', 'pit', 'geotech')):
            return 'soil', 'Proxy inside excavation/geotech container treated as soil-like object'
        if any('concrete' in m or 'steel' in m for m in material_names):
            return 'support', 'Proxy material suggests support/structure'
    if any('steel' in m for m in material_names):
        return 'support', 'Material indicates steel support element'
    if any('concrete' in m for m in material_names):
        return 'wall', 'Material indicates concrete structural element'
    return 'soil', 'Fallback role'


def suggest_material_name(role: str, library: Iterable[MaterialDefinition]) -> str | None:
    names = {item.name: item for item in library}
    preferred = {
        'soil': ['Soil_HSsmall', 'Soil_MC'],
        'wall': ['Wall_Elastic'],
        'slab': ['Wall_Elastic'],
        'beam': ['Wall_Elastic'],
        'column': ['Wall_Elastic'],
        'support': ['Wall_Elastic'],
        'boundary': [None],
        'opening': [None],
    }.get(role, [None])
    for name in preferred:
        if name is None:
            return None
        if name in names:
            return name
    for item in library:
        lname = item.name.lower()
        if role == 'soil' and ('soil' in lname or 'hs' in lname or 'mc' in lname):
            return item.name
        if role != 'soil' and ('wall' in lname or 'elastic' in lname or 'struct' in lname):
            return item.name
    return None


def build_suggestions(model: SimulationModel) -> list[ObjectSuggestion]:
    out: list[ObjectSuggestion] = []
    for rec in model.object_records:
        role, reason = suggest_role(rec)
        material_name = suggest_material_name(role, model.material_library)
        out.append(ObjectSuggestion(object_key=rec.key, role=role, region_name=rec.region_name, material_definition=material_name, reason=reason))
    return out


def apply_suggestion_subset(
    model: SimulationModel,
    suggestions: Sequence[ObjectSuggestion],
    accepted_keys: Iterable[str] | None = None,
    assign_materials: bool = True,
) -> list[ObjectSuggestion]:
    accepted = set(accepted_keys or [s.object_key for s in suggestions])
    applied: list[ObjectSuggestion] = []
    by_key = {s.object_key: s for s in suggestions if s.object_key in accepted}
    for rec in model.object_records:
        sug = by_key.get(rec.key)
        if sug is None:
            continue
        rec.metadata.setdefault('suggested_role', sug.role)
        rec.metadata['role'] = sug.role
        rec.metadata['suggestion_reason'] = sug.reason
        if assign_materials and sug.region_name and sug.material_definition:
            try:
                model.assign_material_definition([sug.region_name], sug.material_definition)
            except Exception:
                pass
        applied.append(sug)
    return applied


def apply_suggestions(model: SimulationModel, assign_materials: bool = True) -> list[ObjectSuggestion]:
    suggestions = build_suggestions(model)
    apply_suggestion_subset(model, suggestions, assign_materials=assign_materials)
    return suggestions
