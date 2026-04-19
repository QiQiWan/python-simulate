from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from geoai_simkit.core.model import InterfaceDefinition, SimulationModel
from geoai_simkit.geometry.demo_pit import AUTO_WALL_SOURCE, build_demo_wall_interfaces
from geoai_simkit.pipeline.adjacency import compute_region_adjacency, compute_region_boundary_adjacency
from geoai_simkit.pipeline.surfaces import compute_region_surface_interface_candidates
from geoai_simkit.pipeline.preprocess import build_node_pair_contact
from geoai_simkit.pipeline.selectors import resolve_region_selector
from geoai_simkit.pipeline.specs import InterfaceGeneratorSpec

InterfaceGenerator = Callable[[SimulationModel, dict[str, Any]], list[InterfaceDefinition]]

_INTERFACE_GENERATORS: dict[str, InterfaceGenerator] = {}


def register_interface_generator(kind: str, generator: InterfaceGenerator) -> None:
    key = str(kind).strip().lower()
    if not key:
        raise ValueError('Interface generator kind must be a non-empty string.')
    _INTERFACE_GENERATORS[key] = generator


def registered_interface_generators() -> tuple[str, ...]:
    return tuple(sorted(_INTERFACE_GENERATORS))


def resolve_registered_interface_generator(kind: str) -> InterfaceGenerator:
    key = str(kind).strip().lower()
    try:
        return _INTERFACE_GENERATORS[key]
    except KeyError as exc:
        raise KeyError(f'Unknown interface generator kind: {kind!r}') from exc


def _generator_metadata(spec: InterfaceGeneratorSpec) -> dict[str, Any]:
    meta = dict(spec.metadata or {})
    meta.setdefault('generator_kind', spec.kind)
    return meta


def _append_interface_metadata(items: list[InterfaceDefinition], *, generator_meta: dict[str, Any]) -> list[InterfaceDefinition]:
    out: list[InterfaceDefinition] = []
    for item in items:
        meta = dict(item.metadata or {})
        for key, value in generator_meta.items():
            meta.setdefault(str(key), value)
        out.append(replace(item, metadata=meta))
    return out


def _single_contact_pair(model: SimulationModel, parameters: dict[str, Any]) -> list[InterfaceDefinition]:
    slave_region = str(parameters.get('slave_region') or '').strip()
    master_region = str(parameters.get('master_region') or '').strip()
    if not slave_region or not master_region or slave_region == master_region:
        return []
    interface = build_node_pair_contact(
        model,
        slave_region=slave_region,
        master_region=master_region,
        active_stages=tuple(str(v) for v in parameters.get('active_stages', ())),
        parameters=dict(parameters.get('parameters') or {}),
        name=str(parameters.get('name') or f'{slave_region}_to_{master_region}'),
        search_radius_factor=float(parameters.get('search_radius_factor', 1.75)),
        exact_only=bool(parameters.get('exact_only', False)),
        metadata=dict(parameters.get('metadata') or {}),
    )
    return [interface] if interface is not None else []


def _selector_contact_pairs(model: SimulationModel, parameters: dict[str, Any]) -> list[InterfaceDefinition]:
    slave_region = str(parameters.get('slave_region') or '').strip()
    master_region = str(parameters.get('master_region') or '').strip()
    slave_selector = parameters.get('slave_selector')
    master_selector = parameters.get('master_selector')
    slave_regions: list[str] = [slave_region] if slave_region else []
    master_regions: list[str] = [master_region] if master_region else []
    if slave_selector is not None:
        slave_regions.extend(resolve_region_selector(model, slave_selector))
    if master_selector is not None:
        master_regions.extend(resolve_region_selector(model, master_selector))
    slave_regions = list(dict.fromkeys(str(v) for v in slave_regions if str(v)))
    master_regions = list(dict.fromkeys(str(v) for v in master_regions if str(v)))
    allow_self_pairs = bool(parameters.get('allow_self_pairs', False))
    name_root = str(parameters.get('name') or 'contact_pair')
    active_stages = tuple(str(v) for v in parameters.get('active_stages', ()))
    iface_parameters = dict(parameters.get('parameters') or {})
    iface_metadata = dict(parameters.get('metadata') or {})
    search_radius_factor = float(parameters.get('search_radius_factor', 1.75))
    exact_only = bool(parameters.get('exact_only', False))
    out: list[InterfaceDefinition] = []
    for slave in slave_regions:
        for master in master_regions:
            if slave == master and not allow_self_pairs:
                continue
            name = name_root if len(slave_regions) == 1 and len(master_regions) == 1 else f'{name_root}:{slave}->{master}'
            interface = build_node_pair_contact(
                model,
                slave_region=slave,
                master_region=master,
                active_stages=active_stages,
                parameters=iface_parameters,
                name=name,
                search_radius_factor=search_radius_factor,
                exact_only=exact_only,
                metadata=iface_metadata,
            )
            if interface is not None:
                out.append(interface)
    return out




def _adjacent_region_contact_pairs(model: SimulationModel, parameters: dict[str, Any]) -> list[InterfaceDefinition]:
    left_region = str(parameters.get('slave_region') or parameters.get('left_region') or '').strip()
    right_region = str(parameters.get('master_region') or parameters.get('right_region') or '').strip()
    left_selector = parameters.get('slave_selector') or parameters.get('left_selector')
    right_selector = parameters.get('master_selector') or parameters.get('right_selector')
    selector = parameters.get('selector')
    region_names = tuple(str(v) for v in parameters.get('region_names', ()))
    min_shared_points = int(parameters.get('min_shared_points', 4))
    active_stages = tuple(str(v) for v in parameters.get('active_stages', ()))
    iface_parameters = dict(parameters.get('parameters') or {})
    iface_metadata = dict(parameters.get('metadata') or {})
    search_radius_factor = float(parameters.get('search_radius_factor', 1.75))
    exact_only = bool(parameters.get('exact_only', False))
    avoid_identical_pairs = bool(parameters.get('avoid_identical_pairs', True))
    name_root = str(parameters.get('name') or 'adjacent_contact')
    adjacencies = compute_region_adjacency(
        model,
        selector=selector,
        region_names=region_names,
        left_selector=left_selector,
        left_region_names=((left_region,) if left_region else ()),
        right_selector=right_selector,
        right_region_names=((right_region,) if right_region else ()),
        min_shared_points=min_shared_points,
    )
    out: list[InterfaceDefinition] = []
    for item in adjacencies:
        name = name_root if len(adjacencies) == 1 else f'{name_root}:{item.region_a}->{item.region_b}'
        meta = dict(iface_metadata)
        meta.update({
            'adjacency_shared_point_count': int(item.shared_point_count),
            'adjacency_centroid_distance': float(item.centroid_distance),
            'adjacency_shared_point_ids': tuple(int(v) for v in item.shared_point_ids),
            'adjacency_generated_by': 'pipeline.adjacent_region_contact_pairs',
        })
        interface = build_node_pair_contact(
            model,
            slave_region=item.region_a,
            master_region=item.region_b,
            active_stages=active_stages,
            parameters=iface_parameters,
            name=name,
            search_radius_factor=search_radius_factor,
            exact_only=exact_only,
            avoid_identical_pairs=avoid_identical_pairs,
            metadata=meta,
        )
        if interface is not None:
            out.append(interface)
    return out



def _boundary_adjacent_region_contact_pairs(model: SimulationModel, parameters: dict[str, Any]) -> list[InterfaceDefinition]:
    left_region = str(parameters.get('slave_region') or parameters.get('left_region') or '').strip()
    right_region = str(parameters.get('master_region') or parameters.get('right_region') or '').strip()
    left_selector = parameters.get('slave_selector') or parameters.get('left_selector')
    right_selector = parameters.get('master_selector') or parameters.get('right_selector')
    selector = parameters.get('selector')
    region_names = tuple(str(v) for v in parameters.get('region_names', ()))
    min_shared_faces = int(parameters.get('min_shared_faces', 1))
    active_stages = tuple(str(v) for v in parameters.get('active_stages', ()))
    iface_parameters = dict(parameters.get('parameters') or {})
    iface_metadata = dict(parameters.get('metadata') or {})
    search_radius_factor = float(parameters.get('search_radius_factor', 1.75))
    exact_only = bool(parameters.get('exact_only', False))
    avoid_identical_pairs = bool(parameters.get('avoid_identical_pairs', True))
    name_root = str(parameters.get('name') or 'boundary_adjacent_contact')
    adjacencies = compute_region_boundary_adjacency(
        model,
        selector=selector,
        region_names=region_names,
        left_selector=left_selector,
        left_region_names=((left_region,) if left_region else ()),
        right_selector=right_selector,
        right_region_names=((right_region,) if right_region else ()),
        min_shared_faces=min_shared_faces,
    )
    out: list[InterfaceDefinition] = []
    for item in adjacencies:
        name = name_root if len(adjacencies) == 1 else f'{name_root}:{item.region_a}->{item.region_b}'
        meta = dict(iface_metadata)
        meta.update({
            'boundary_adjacency_shared_face_count': int(item.shared_face_count),
            'boundary_adjacency_shared_point_count': int(item.shared_point_count),
            'boundary_adjacency_shared_face_area': float(item.shared_face_area),
            'boundary_adjacency_generated_by': 'pipeline.boundary_adjacent_region_contact_pairs',
        })
        boundary_ids = tuple(int(v) for v in item.shared_boundary_point_ids)
        interface = build_node_pair_contact(
            model,
            slave_region=item.region_a,
            master_region=item.region_b,
            active_stages=active_stages,
            parameters=iface_parameters,
            name=name,
            search_radius_factor=search_radius_factor,
            exact_only=exact_only,
            avoid_identical_pairs=avoid_identical_pairs,
            slave_point_subset=boundary_ids,
            master_point_subset=None,
            metadata=meta,
        )
        if interface is not None:
            out.append(interface)
    return out



def _surface_boundary_adjacent_contact_pairs(model: SimulationModel, parameters: dict[str, Any]) -> list[InterfaceDefinition]:
    left_region = str(parameters.get('slave_region') or parameters.get('left_region') or '').strip()
    right_region = str(parameters.get('master_region') or parameters.get('right_region') or '').strip()
    left_selector = parameters.get('slave_selector') or parameters.get('left_selector')
    right_selector = parameters.get('master_selector') or parameters.get('right_selector')
    selector = parameters.get('selector')
    region_names = tuple(str(v) for v in parameters.get('region_names', ()))
    min_shared_faces = int(parameters.get('min_shared_faces', 1))
    active_stages = tuple(str(v) for v in parameters.get('active_stages', ()))
    iface_parameters = dict(parameters.get('parameters') or {})
    iface_metadata = dict(parameters.get('metadata') or {})
    search_radius_factor = float(parameters.get('search_radius_factor', 1.75))
    exact_only = bool(parameters.get('exact_only', False))
    avoid_identical_pairs = bool(parameters.get('avoid_identical_pairs', True))
    name_root = str(parameters.get('name') or 'surface_adjacent_contact')
    candidates = compute_region_surface_interface_candidates(
        model,
        selector=selector,
        region_names=region_names,
        left_selector=left_selector,
        left_region_names=((left_region,) if left_region else ()),
        right_selector=right_selector,
        right_region_names=((right_region,) if right_region else ()),
        min_shared_faces=min_shared_faces,
    )
    out: list[InterfaceDefinition] = []
    for item in candidates:
        name = name_root if len(candidates) == 1 else f'{name_root}:{item.region_a}->{item.region_b}'
        meta = dict(iface_metadata)
        meta.update({
            'surface_candidate_shared_face_count': int(item.shared_face_count),
            'surface_candidate_shared_face_area': float(item.shared_face_area),
            'surface_candidate_shared_point_count': int(len(item.shared_boundary_point_ids)),
            'surface_candidate_centroid_distance': float(item.centroid_distance),
            'surface_candidate_generated_by': 'pipeline.surface_boundary_adjacent_contact_pairs',
        })
        interface = build_node_pair_contact(
            model,
            slave_region=item.region_a,
            master_region=item.region_b,
            active_stages=active_stages,
            parameters=iface_parameters,
            name=name,
            search_radius_factor=search_radius_factor,
            exact_only=exact_only,
            avoid_identical_pairs=avoid_identical_pairs,
            slave_point_subset=item.slave_surface_point_ids,
            master_point_subset=item.master_boundary_point_ids,
            metadata=meta,
        )
        if interface is not None:
            out.append(interface)
    return out

def _demo_wall_interface_generator(model: SimulationModel, parameters: dict[str, Any]) -> list[InterfaceDefinition]:
    policy = parameters.get('interface_policy')
    if parameters.get('enabled_groups') is not None:
        model.metadata['demo_enabled_interface_groups'] = list(parameters.get('enabled_groups') or [])
    if parameters.get('region_overrides') is not None:
        model.metadata['demo_interface_region_overrides'] = dict(parameters.get('region_overrides') or {})
    if parameters.get('nearest_radius_factor') is not None:
        model.metadata['demo_interface_nearest_radius_factor'] = float(parameters.get('nearest_radius_factor'))
    items = build_demo_wall_interfaces(model, interface_policy=str(policy) if policy is not None else None)
    default_meta = {'generator_kind': 'demo_wall_interfaces', 'source': AUTO_WALL_SOURCE}
    return _append_interface_metadata(items, generator_meta=default_meta)


def resolve_interface_entries(model: SimulationModel, entries: tuple[InterfaceDefinition | InterfaceGeneratorSpec, ...]) -> tuple[list[InterfaceDefinition], list[str], list[str]]:
    resolved: list[InterfaceDefinition] = []
    generated_names: list[str] = []
    notes: list[str] = []
    for entry in entries:
        if isinstance(entry, InterfaceDefinition):
            resolved.append(entry)
            continue
        generator = resolve_registered_interface_generator(entry.kind)
        items = _append_interface_metadata(generator(model, dict(entry.parameters or {})), generator_meta=_generator_metadata(entry))
        if not items:
            notes.append(f'Interface generator {entry.kind!r} produced no interfaces.')
            continue
        resolved.extend(items)
        generated_names.extend(item.name for item in items)
    return resolved, generated_names, notes


register_interface_generator('contact_pair', _single_contact_pair)
register_interface_generator('selector_contact_pairs', _selector_contact_pairs)
register_interface_generator('adjacent_region_contact_pairs', _adjacent_region_contact_pairs)
register_interface_generator('boundary_adjacent_region_contact_pairs', _boundary_adjacent_region_contact_pairs)
register_interface_generator('surface_boundary_adjacent_contact_pairs', _surface_boundary_adjacent_contact_pairs)
register_interface_generator('demo_wall_interfaces', _demo_wall_interface_generator)
