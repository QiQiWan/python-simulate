from __future__ import annotations

"""Meshio-backed geology mesh importer for .msh and .vtu sources.

The importer treats mesh files as imported geological domains.  Volume-cell
files (.msh/.vtu with tetra/hexa/wedge/pyramid cells) become solver-mesh
candidates; surface-only files remain geometry/visualization candidates and are
marked as requiring volume remeshing.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from geoai_simkit.geology.importers.contracts import GeologyImportDiagnostic, GeologyImportRequest, GeologyImportResult
from geoai_simkit.geoproject import GeoProjectDocument, GeometryVolume, GeometrySurface, SoilCluster, SoilContour, MaterialRecord
from geoai_simkit.mesh.mesh_document import MeshDocument, MeshQualityReport
from geoai_simkit.mesh.fem_quality import add_geology_layer_tags, analyze_mesh_for_fem
from geoai_simkit.mesh.mesh_entity_map import MeshEntityMap

_VOLUME_CELL_TYPES = {"tetra", "tetra10", "hexahedron", "hexahedron20", "wedge", "wedge15", "pyramid", "pyramid13"}
_SURFACE_CELL_TYPES = {"triangle", "triangle6", "quad", "quad8", "quad9"}


@dataclass(slots=True)
class _SimpleCellBlock:
    type: str
    data: list[list[int]]


@dataclass(slots=True)
class _SimpleMesh:
    points: list[tuple[float, float, float]]
    cells: list[_SimpleCellBlock]
    metadata: dict[str, Any] | None = None


def _chunk(values: list[float], size: int) -> list[tuple[float, float, float]]:
    out: list[tuple[float, float, float]] = []
    for idx in range(0, len(values), size):
        row = values[idx: idx + size]
        if not row:
            continue
        x = float(row[0]) if len(row) > 0 else 0.0
        y = float(row[1]) if len(row) > 1 else 0.0
        z = float(row[2]) if len(row) > 2 else 0.0
        out.append((x, y, z))
    return out


def _numbers(text: str | None, cast: Any = float) -> list[Any]:
    if not text:
        return []
    return [cast(part) for part in text.replace('\n', ' ').split() if part.strip()]


def _parse_ascii_vtu(path: Path) -> _SimpleMesh:
    tree = ET.parse(path)
    root = tree.getroot()
    pieces = root.findall('.//Piece')
    if not pieces:
        raise ValueError(f'VTU 文件缺少 Piece: {path}')
    all_points: list[tuple[float, float, float]] = []
    by_type: dict[str, list[list[int]]] = {}
    cell_data_raw: dict[str, list[Any]] = {}
    point_data_raw: dict[str, list[Any]] = {}
    active_cell_scalar = ''
    active_point_scalar = ''
    vtk_to_name = {
        1: 'vertex',
        3: 'line',
        5: 'triangle',
        9: 'quad',
        10: 'tetra',
        12: 'hexahedron',
        13: 'wedge',
        14: 'pyramid',
        21: 'quadratic_edge',
        22: 'triangle6',
        23: 'quad8',
        24: 'tetra10',
        25: 'hexahedron20',
        26: 'wedge15',
        27: 'pyramid13',
        28: 'quad9',
    }
    for piece in pieces:
        point_offset = len(all_points)
        points_array = piece.find('./Points/DataArray')
        if points_array is None:
            raise ValueError(f'VTU 文件缺少 Points/DataArray: {path}')
        ncomp = int(points_array.attrib.get('NumberOfComponents', '3') or '3')
        points = _chunk(_numbers(points_array.text, float), ncomp)
        all_points.extend(points)
        arrays: dict[str, list[int]] = {}
        for data_array in piece.findall('./Cells/DataArray'):
            name = str(data_array.attrib.get('Name', '')).strip().lower()
            if name:
                arrays[name] = _numbers(data_array.text, int)
        connectivity = arrays.get('connectivity', [])
        offsets = arrays.get('offsets', [])
        vtk_types = arrays.get('types', [])
        grouped_original_indices: dict[str, list[int]] = {}
        start = 0
        for cell_idx, end in enumerate(offsets):
            raw = connectivity[start:int(end)]
            start = int(end)
            vtk_type = int(vtk_types[cell_idx]) if cell_idx < len(vtk_types) else 0
            name = vtk_to_name.get(vtk_type, f'vtk_{vtk_type}')
            by_type.setdefault(name, []).append([int(v) + point_offset for v in raw])
            grouped_original_indices.setdefault(name, []).append(cell_idx)
        cell_data_el = piece.find('./CellData')
        if cell_data_el is not None and not active_cell_scalar:
            active_cell_scalar = str(cell_data_el.attrib.get('Scalars', '') or '').strip()
        local_cell_data: dict[str, list[Any]] = {}
        total_cells = len(offsets)
        if cell_data_el is not None:
            for data_array in cell_data_el.findall('./DataArray'):
                name = str(data_array.attrib.get('Name', '')).strip()
                if not name:
                    continue
                dtype = str(data_array.attrib.get('type', '')).lower()
                caster = float if 'float' in dtype else int
                values = _numbers(data_array.text, caster)
                if len(values) == total_cells:
                    local_cell_data[name] = values
        for kind, original_indices in grouped_original_indices.items():
            for original_idx in original_indices:
                for name, values in local_cell_data.items():
                    cell_data_raw.setdefault(name, []).append(values[original_idx])
        point_data_el = piece.find('./PointData')
        if point_data_el is not None and not active_point_scalar:
            active_point_scalar = str(point_data_el.attrib.get('Scalars', '') or '').strip()
        if point_data_el is not None:
            for data_array in point_data_el.findall('./DataArray'):
                name = str(data_array.attrib.get('Name', '')).strip()
                if not name:
                    continue
                n_components = int(data_array.attrib.get('NumberOfComponents', '1') or '1')
                if n_components != 1:
                    continue
                dtype = str(data_array.attrib.get('type', '')).lower()
                caster = float if 'float' in dtype else int
                values = _numbers(data_array.text, caster)
                if len(values) == len(points):
                    point_data_raw.setdefault(name, []).extend(values)
    cells = [_SimpleCellBlock(kind, rows) for kind, rows in by_type.items()]
    return _SimpleMesh(
        points=all_points,
        cells=cells,
        metadata={
            'fallback_reader': 'ascii_vtu',
            'source_path': str(path),
            'cell_data': cell_data_raw,
            'point_data': point_data_raw,
            'active_cell_scalar': active_cell_scalar,
            'active_point_scalar': active_point_scalar,
        },
    )


def _parse_gmsh_v2(path: Path) -> _SimpleMesh:
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    idx = 0
    node_id_to_index: dict[int, int] = {}
    points: list[tuple[float, float, float]] = []
    by_type: dict[str, list[list[int]]] = {}
    by_type_physical: dict[str, list[int]] = {}
    gmsh_to_name = {
        1: 'line',
        2: 'triangle',
        3: 'quad',
        4: 'tetra',
        5: 'hexahedron',
        6: 'wedge',
        7: 'pyramid',
        9: 'triangle6',
        11: 'tetra10',
        16: 'quad8',
        17: 'hexahedron20',
        18: 'wedge15',
        19: 'pyramid13',
    }
    while idx < len(lines):
        line = lines[idx].strip()
        if line == '$Nodes':
            idx += 1
            count = int(lines[idx].strip())
            idx += 1
            for _ in range(count):
                parts = lines[idx].split()
                node_id = int(parts[0])
                coords = (float(parts[1]), float(parts[2]), float(parts[3]))
                node_id_to_index[node_id] = len(points)
                points.append(coords)
                idx += 1
            continue
        if line == '$Elements':
            idx += 1
            count = int(lines[idx].strip())
            idx += 1
            for _ in range(count):
                parts = lines[idx].split()
                elem_type = int(parts[1])
                tag_count = int(parts[2])
                node_ids = [int(v) for v in parts[3 + tag_count:]]
                conn = [node_id_to_index[v] for v in node_ids if v in node_id_to_index]
                if conn:
                    kind = gmsh_to_name.get(elem_type, f'gmsh_{elem_type}')
                    by_type.setdefault(kind, []).append(conn)
                    physical = int(parts[3]) if tag_count >= 1 else 0
                    by_type_physical.setdefault(kind, []).append(physical)
                idx += 1
            continue
        idx += 1
    if not points:
        raise ValueError(f'Gmsh 文件缺少节点: {path}')
    cells = [_SimpleCellBlock(kind, rows) for kind, rows in by_type.items()]
    cell_data: dict[str, list[int]] = {'gmsh_physical': []}
    for kind in by_type:
        cell_data['gmsh_physical'].extend(by_type_physical.get(kind, [0] * len(by_type[kind])))
    return _SimpleMesh(points=points, cells=cells, metadata={'fallback_reader': 'gmsh_v2_ascii', 'source_path': str(path), 'cell_data': cell_data})


def _read_meshio_fallback(path: Path) -> _SimpleMesh:
    suffix = path.suffix.lower()
    if suffix == '.vtu':
        return _parse_ascii_vtu(path)
    if suffix == '.msh':
        return _parse_gmsh_v2(path)
    raise RuntimeError(f'没有可用 meshio，且内置 fallback 不支持格式: {suffix}')


def _safe_id(value: Any, fallback: str = "mesh_geology") -> str:
    chars = [ch.lower() if ch.isalnum() else "_" for ch in str(value or fallback).strip()]
    out = "".join(chars).strip("_") or fallback
    while "__" in out:
        out = out.replace("__", "_")
    if out[0].isdigit():
        out = f"{fallback}_{out}"
    return out


def _bounds(points: list[tuple[float, float, float]]) -> tuple[float, float, float, float, float, float]:
    if not points:
        return (0.0, 1.0, 0.0, 1.0, -1.0, 0.0)
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def _read_meshio(path: Path) -> Any:
    try:
        import meshio  # type: ignore
        return meshio.read(path)
    except Exception as exc:  # pragma: no cover - environment dependent
        # Keep the desktop importer usable even when meshio is missing or when
        # meshio itself rejects a simple ASCII VTU/Gmsh v2 file.  The fallback is
        # intentionally conservative: it reads points and common volume/surface
        # cell connectivity only, which is enough for geology visualization,
        # bounds, mesh replacement and downstream remeshing readiness.
        try:
            return _read_meshio_fallback(path)
        except Exception:
            raise RuntimeError("导入 .msh/.vtu 需要 meshio，或可被内置 ASCII VTU/Gmsh v2 fallback 解析的文件。") from exc



def _flatten_meshio_cell_data(mesh: Any, cell_block_ranges: list[dict[str, Any]], total_cells: int) -> dict[str, list[Any]]:
    """Return cell-data arrays aligned with MeshDocument.cells.

    meshio stores cell_data as ``{name: [array_per_cell_block, ...]}``, while
    our MeshDocument stores a single flattened cell list.  The fallback readers
    already provide flattened arrays in ``metadata['cell_data']``.  This helper
    preserves real geology tags such as ``soil_id`` and Gmsh physical tags so
    the GUI can reproduce ParaView-like categorical layer coloring.
    """
    meta = dict(getattr(mesh, 'metadata', {}) or {})
    out: dict[str, list[Any]] = {}
    fallback = meta.get('cell_data')
    if isinstance(fallback, dict):
        for name, values in fallback.items():
            vals = list(values or [])
            if len(vals) == total_cells:
                out[str(name)] = vals
    raw = getattr(mesh, 'cell_data', None)
    if isinstance(raw, dict):
        for name, blocks in raw.items():
            vals: list[Any] = []
            try:
                iterable = list(blocks)
            except Exception:
                iterable = []
            for block in iterable:
                try:
                    vals.extend(list(block))
                except Exception:
                    pass
            if len(vals) == total_cells:
                # Convert numpy scalar types to plain Python values for JSON and
                # Qt table display stability.
                clean: list[Any] = []
                for v in vals:
                    try:
                        clean.append(v.item())  # numpy scalar
                    except Exception:
                        clean.append(v)
                out[str(name)] = clean
    return out


def _clean_scalar_values(values: list[Any]) -> list[Any]:
    clean: list[Any] = []
    for v in values:
        try:
            clean.append(v.item())  # numpy scalar
        except Exception:
            clean.append(v)
    return clean


def _flatten_meshio_point_data(mesh: Any, point_count: int) -> dict[str, list[Any]]:
    """Return point-data arrays aligned with MeshDocument.nodes.

    Some ParaView VTU exports store geology/material labels on points instead of
    cells.  The GUI still needs cell-level categories for surface coloring, so
    these arrays are preserved as node_tags and later projected onto cells.
    """
    meta = dict(getattr(mesh, 'metadata', {}) or {})
    out: dict[str, list[Any]] = {}
    fallback = meta.get('point_data')
    if isinstance(fallback, dict):
        for name, values in fallback.items():
            vals = list(values or [])
            if len(vals) == point_count:
                out[str(name)] = vals
    raw = getattr(mesh, 'point_data', None)
    if isinstance(raw, dict):
        for name, values in raw.items():
            try:
                vals = list(values)
            except Exception:
                vals = []
            if len(vals) == point_count:
                out[str(name)] = _clean_scalar_values(vals)
    return out


def _mode_for_cell(values: list[Any], cell: tuple[int, ...]) -> Any:
    counts: dict[str, tuple[Any, int]] = {}
    for node_id in cell:
        if int(node_id) < 0 or int(node_id) >= len(values):
            continue
        raw = values[int(node_id)]
        key = str(raw)
        current = counts.get(key)
        counts[key] = (raw, 1 if current is None else current[1] + 1)
    if not counts:
        return ''
    return sorted(counts.values(), key=lambda row: (-row[1], str(row[0])))[0][0]


def _scalar_unique_count(values: list[Any]) -> int:
    return len({str(v) for v in values})


def _looks_like_geology_scalar(name: str) -> bool:
    lower = str(name or '').lower().replace('-', '_').replace(':', '_').replace(' ', '_')
    if lower.startswith('vtk') or lower in {'connectivity', 'offsets', 'types'}:
        return False
    tokens = (
        'soil', 'stratum', 'strata', 'layer', 'geology', 'geo', 'lithology',
        'formation', 'material', 'mat', 'rock', 'phase', 'physical', 'gmsh',
        'region', 'domain', 'zone', 'group', 'unit', 'facies',
    )
    return any(token in lower for token in tokens)


def _preferred_geology_scalar(cell_tags: dict[str, list[Any]], cell_count: int, *, metadata: dict[str, Any] | None = None) -> str | None:
    meta = dict(metadata or {})
    candidates = (
        str(meta.get('active_cell_scalar') or ''),
        str(meta.get('active_point_scalar_cell') or ''),
        str(meta.get('preferred_geology_scalar') or ''),
        'soil_id', 'soilid', 'soil', 'soil_layer', 'soil_layer_id',
        'stratum_id', 'stratum', 'strata', 'strata_id',
        'layer_id', 'layer', 'geology_layer', 'geology_layer_id',
        'lithology', 'formation', 'formation_id', 'facies',
        'material_index', 'material_id', 'materialid', 'material', 'mat_id', 'mat',
        'gmsh_physical', 'gmsh:physical', 'physical', 'physical_group', 'physical_id',
        'domain', 'domain_id', 'region', 'region_id', 'zone', 'zone_id',
        'display_group',
    )
    lower_to_key = {str(k).lower().replace('-', '_').replace(':', '_').replace(' ', '_'): k for k in cell_tags}
    exact: list[str] = []
    for name in candidates:
        if not name:
            continue
        key = lower_to_key.get(str(name).lower().replace('-', '_').replace(':', '_').replace(' ', '_'))
        if key is not None and len(list(cell_tags.get(key, []))) == cell_count:
            exact.append(str(key))
    fuzzy = [str(key) for key, values in cell_tags.items() if len(list(values)) == cell_count and _looks_like_geology_scalar(str(key))]
    ordered = list(dict.fromkeys(exact + fuzzy))
    if not ordered:
        return None
    multi = [key for key in ordered if _scalar_unique_count(list(cell_tags.get(key, []))) > 1]
    return multi[0] if multi else ordered[0]


def _cell_type_name(cell_type: str) -> str:
    lower = str(cell_type or "").lower()
    aliases = {
        "tetra": "tet4",
        "tetra10": "tet10",
        "hexahedron": "hex8",
        "hexahedron20": "hex20",
        "triangle": "tri3",
        "triangle6": "tri6",
        "quad": "quad4",
        "quad8": "quad8",
        "quad9": "quad9",
        "wedge": "wedge6",
        "wedge15": "wedge15",
        "pyramid": "pyramid5",
        "pyramid13": "pyramid13",
        "line": "line2",
    }
    return aliases.get(lower, lower or "unknown")


def _to_mesh_document(mesh: Any, *, block_id: str, source_path: str) -> tuple[MeshDocument, dict[str, Any]]:
    points: list[tuple[float, float, float]] = []
    raw_points = getattr(mesh, "points", None)
    if raw_points is None:
        raw_points = []
    for row in list(raw_points):
        values = list(row)
        x = float(values[0]) if len(values) > 0 else 0.0
        y = float(values[1]) if len(values) > 1 else 0.0
        z = float(values[2]) if len(values) > 2 else 0.0
        points.append((x, y, z))

    cells: list[tuple[int, ...]] = []
    cell_types: list[str] = []
    source_cell_types: list[str] = []
    cell_block_ranges: list[dict[str, Any]] = []
    raw_blocks = getattr(mesh, "cells", None)
    if raw_blocks is None:
        raw_blocks = []
    for block in list(raw_blocks):
        raw_type = str(getattr(block, "type", "unknown"))
        data = getattr(block, "data", None)
        if data is None:
            data = []
        start = len(cells)
        for conn in list(data):
            cells.append(tuple(int(v) for v in list(conn)))
            cell_types.append(_cell_type_name(raw_type))
        end = len(cells)
        if end > start:
            source_cell_types.append(raw_type)
            cell_block_ranges.append({"source_type": raw_type, "mapped_type": _cell_type_name(raw_type), "start": start, "end": end})

    block_tags = [block_id for _ in cells]
    source_type_tags = [row.get("mapped_type") for row in cell_block_ranges for _ in range(int(row.get("end", 0)) - int(row.get("start", 0)))]
    cell_tags: dict[str, list[Any]] = {"block_id": block_tags, "source_cell_type": source_type_tags}
    imported_cell_data = _flatten_meshio_cell_data(mesh, cell_block_ranges, len(cells))
    for name, values in imported_cell_data.items():
        if len(values) == len(cells):
            cell_tags[str(name)] = values

    imported_point_data = _flatten_meshio_point_data(mesh, len(points))
    node_tags: dict[str, list[Any]] = {}
    point_derived_cell_tags: dict[str, list[Any]] = {}
    for name, values in imported_point_data.items():
        if len(values) != len(points):
            continue
        node_tags[str(name)] = list(values)
        derived_name = f"{name}_from_points"
        projected = [_mode_for_cell(list(values), tuple(cell)) for cell in cells]
        if len(projected) == len(cells):
            point_derived_cell_tags[derived_name] = projected
            # If the VTU active scalar lives on points, keep a direct cell alias
            # too so categorical lookup behaves like ParaView's point-to-cell
            # coloring for imported geology labels.
            active_point = str(dict(getattr(mesh, "metadata", {}) or {}).get("active_point_scalar") or "")
            if active_point and active_point == str(name):
                cell_tags[str(name)] = projected
    for name, values in point_derived_cell_tags.items():
        if len(values) == len(cells) and name not in cell_tags:
            cell_tags[str(name)] = values

    raw_meta = dict(getattr(mesh, "metadata", {}) or {})
    selection_meta = {
        "active_cell_scalar": raw_meta.get("active_cell_scalar"),
        "active_point_scalar_cell": f"{raw_meta.get('active_point_scalar')}_from_points" if raw_meta.get("active_point_scalar") else "",
    }
    preferred_scalar = _preferred_geology_scalar(cell_tags, len(cells), metadata=selection_meta)
    if preferred_scalar and preferred_scalar not in {"geology_layer_id", "display_group"}:
        base = [str(v) for v in cell_tags[preferred_scalar]]
        cell_tags["geology_layer_id"] = base
        cell_tags["display_group"] = base
    entity_map = MeshEntityMap(block_to_cells={block_id: list(range(len(cells)))}, metadata={"source": "meshio_geology_importer", "source_path": source_path})
    metadata = {
        "source": "meshio_geology_importer",
        "source_path": source_path,
        "meshio_cell_types": source_cell_types,
        "cell_block_ranges": cell_block_ranges,
        "fallback_reader": raw_meta.get("fallback_reader"),
        "active_cell_scalar": raw_meta.get("active_cell_scalar"),
        "active_point_scalar": raw_meta.get("active_point_scalar"),
        "imported_cell_data_names": sorted(imported_cell_data.keys()),
        "imported_point_data_names": sorted(imported_point_data.keys()),
        "point_derived_cell_data_names": sorted(point_derived_cell_tags.keys()),
        "preferred_geology_scalar": preferred_scalar,
    }
    mesh_doc = MeshDocument(
        nodes=points,
        cells=cells,
        cell_types=cell_types,
        cell_tags=cell_tags,
        node_tags=node_tags,
        entity_map=entity_map,
        quality=MeshQualityReport(warnings=[] if cells else ["Imported mesh has no supported cells."]),
        metadata=metadata,
    )
    return mesh_doc, metadata


class MeshioGeologyImporter:
    label = "Meshio geological mesh importer"
    source_types = ("meshio_geology", "msh_geology", "vtu_geology", "msh", "vtu", "geology_msh", "geology_vtu")

    def can_import(self, request: GeologyImportRequest) -> bool:
        path = request.source_path
        return path is not None and path.suffix.lower() in {".msh", ".vtu"}

    def import_to_project(self, request: GeologyImportRequest) -> GeologyImportResult:
        path = request.source_path
        if path is None:
            raise ValueError("Meshio geology import requires a filesystem path.")
        mesh = _read_meshio(path)
        project_name = str(request.options.get("project_name") or request.options.get("name") or path.stem)
        material_id = str(request.options.get("material_id", "soil_default") or "soil_default")
        block_id = _safe_id(path.stem, "mesh_geology")
        mesh_doc, mesh_meta = _to_mesh_document(mesh, block_id=block_id, source_path=str(path))
        layer_display = add_geology_layer_tags(mesh_doc)
        quality_report = analyze_mesh_for_fem(mesh_doc)
        bounds = _bounds(mesh_doc.nodes)
        source_types = {str(t).lower() for t in mesh_meta.get("meshio_cell_types", [])}
        has_volume_cells = bool(source_types.intersection(_VOLUME_CELL_TYPES))
        has_surface_cells = bool(source_types.intersection(_SURFACE_CELL_TYPES))
        project = GeoProjectDocument.create_empty(name=project_name)
        xmin, xmax, ymin, ymax, zmin, zmax = bounds
        project.soil_model.soil_contour = SoilContour(
            id="soil_contour_from_meshio",
            name="Soil contour from imported mesh bounds",
            polygon=[(xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)],
            z_top=float(zmax),
            z_bottom=float(zmin),
            metadata={"source": "meshio_bounds"},
        )
        surface_id = f"surface_{block_id}"
        project.geometry_model.surfaces[surface_id] = GeometrySurface(
            id=surface_id,
            name=f"Imported mesh boundary {path.stem}",
            kind="meshio_surface_or_boundary",
            metadata={"source": "meshio_geology_importer", "source_path": str(path), "meshio_cell_types": sorted(source_types)},
        )
        project.geometry_model.volumes[block_id] = GeometryVolume(
            id=block_id,
            name=path.stem,
            bounds=bounds,
            surface_ids=[surface_id],
            role="soil",
            material_id=material_id,
            metadata={
                "source": "meshio_geology_importer",
                "source_path": str(path),
                "mesh_source_format": path.suffix.lower().lstrip("."),
                "volume_mesh_ready": bool(has_volume_cells),
                "surface_mesh_only": bool(has_surface_cells and not has_volume_cells),
                "requires_volume_meshing": bool(not has_volume_cells),
                "meshio_cell_types": sorted(source_types),
                "geology_layer_display": layer_display,
                "fem_quality_report": quality_report.to_dict(),
            },
        )
        project.soil_model.add_cluster(SoilCluster(
            id=f"cluster_{block_id}",
            name=f"Cluster {path.stem}",
            volume_ids=[block_id],
            material_id=material_id,
            layer_id=block_id,
            drainage="drained",
            metadata={"source": "meshio_geology_importer", "volume_mesh_ready": bool(has_volume_cells)},
        ))
        project.material_library.soil_materials[material_id] = MaterialRecord(
            id=material_id,
            name=material_id,
            model_type="mohr_coulomb_placeholder",
            drainage="drained",
            parameters={"gamma_unsat": 18.0, "gamma_sat": 20.0, "E_ref": 30000.0, "nu": 0.3, "c_ref": 10.0, "phi": 30.0},
            metadata={"source": "meshio_import_default"},
        )
        project.mesh_model.mesh_settings.element_family = "imported_volume_mesh" if has_volume_cells else "imported_surface_mesh"
        project.mesh_model.mesh_settings.metadata.update({
            "mesh_role": "imported_geology_mesh",
            "source": "meshio_geology_importer",
            "requires_volume_meshing": bool(not has_volume_cells),
            "solid_solver_ready": bool(has_volume_cells),
            "meshio_cell_types": sorted(source_types),
            "geology_layer_display": layer_display,
            "fem_quality_report": quality_report.to_dict(),
        })
        project.mesh_model.attach_mesh(mesh_doc)
        project.phase_manager.initial_phase.active_blocks.add(block_id)
        project.refresh_phase_snapshot(project.phase_manager.initial_phase.id)
        project.topology_graph.add_node(block_id, "volume", label=path.stem, role="soil", material_id=material_id)
        project.topology_graph.add_node(surface_id, "face", label=surface_id, role="meshio_boundary")
        project.topology_graph.add_edge(block_id, surface_id, "bounded_by", import_source="meshio_geology_importer")
        project.topology_graph.add_node(material_id, "material", label=material_id)
        project.topology_graph.add_edge(block_id, material_id, "mapped_to", relation_group="volume_material")
        diagnostics: list[GeologyImportDiagnostic] = []
        if not mesh_doc.cells:
            diagnostics.append(GeologyImportDiagnostic("warning", "mesh_has_no_cells", "导入的 mesh 没有可用单元。", target=str(path)))
        if not has_volume_cells:
            diagnostics.append(GeologyImportDiagnostic("warning", "surface_mesh_requires_remesh", "导入的是表面/边界网格，求解前需要重新生成体网格。", target=str(path)))
        project.metadata.update({
            "source": "meshio_geology_importer",
            "meshio_geology": {"source_path": str(path), "bounds": list(bounds), "node_count": mesh_doc.node_count, "cell_count": mesh_doc.cell_count, "cell_types": sorted(source_types), "volume_mesh_ready": bool(has_volume_cells), "geology_layer_display": layer_display, "fem_quality_report": quality_report.to_dict()},
            "dirty": True,
            "requires_volume_meshing": bool(not has_volume_cells),
            "solid_solver_ready": bool(has_volume_cells),
        })
        return GeologyImportResult(
            source_type=request.normalized_source_type,
            project=project,
            diagnostics=diagnostics,
            source_path=str(path),
            imported_object_count=1,
            metadata=dict(project.metadata.get("meshio_geology", {})),
        )


__all__ = ["MeshioGeologyImporter"]
