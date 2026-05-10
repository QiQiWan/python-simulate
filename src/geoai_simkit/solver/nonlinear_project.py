from __future__ import annotations

"""Project-level nonlinear soil diagnostics built on the solid FEM result loop.

This module provides a verified engineering-preview path for Mohr-Coulomb soil
state updates.  It does not yet run a full global Newton return-mapping loop; it
post-processes the converged linear strain field through the nonlinear material
law, writes plasticity state fields, and preserves the same solver backend
contract for future global nonlinear assembly.
"""

from typing import Any, Mapping

import numpy as np

from geoai_simkit.materials.base import MaterialState
from geoai_simkit.materials.mohr_coulomb import MohrCoulomb
from geoai_simkit.results.result_package import ResultFieldRecord


def _material_parameters(row: Mapping[str, Any] | None) -> dict[str, float]:
    row = dict(row or {})
    params = dict(row.get("parameters", {}) or {})
    return {
        "E": float(params.get("E", params.get("E_ref", params.get("YoungModulus", 30000.0))) or 30000.0),
        "nu": float(params.get("nu", params.get("poisson", 0.3)) or 0.3),
        "cohesion": float(params.get("cohesion", params.get("c_ref", params.get("c", 10.0))) or 10.0),
        "friction_deg": float(params.get("friction_deg", params.get("phi", params.get("phi_deg", 30.0))) or 30.0),
        "dilation_deg": float(params.get("dilation_deg", params.get("psi", 0.0)) or 0.0),
        "tensile_strength": float(params.get("tensile_strength", 0.0) or 0.0),
        "rho": float(params.get("rho", 0.0) or 0.0),
    }


def _material_by_cell(project: Any) -> dict[int, dict[str, Any]]:
    mesh = getattr(getattr(project, "mesh_model", None), "mesh_document", None)
    library = getattr(project, "material_library", None)
    soils = dict(getattr(library, "soil_materials", {}) or {}) if library is not None else {}
    out: dict[int, dict[str, Any]] = {}
    if mesh is None:
        return out
    mats = list(mesh.cell_tags.get("material_id", []) or [])
    for cid, mid in enumerate(mats):
        record = soils.get(str(mid))
        if record is not None and hasattr(record, "to_dict"):
            out[cid] = record.to_dict()
        else:
            out[cid] = {"id": str(mid), "model_type": "mohr_coulomb", "parameters": {}}
    return out


def apply_mohr_coulomb_state_update(project: Any, *, source_backend: str = "solid_linear_static_cpu") -> dict[str, Any]:
    """Write Mohr-Coulomb plasticity fields to project ResultStore.

    The function uses each stage's ``cell_strain`` field as the strain increment
    and evaluates the built-in Mohr-Coulomb model cell-by-cell.  It is a
    deterministic engineering-preview bridge between the current linear global
    solve and the existing nonlinear material library.
    """

    result_store = getattr(project, "result_store", None)
    if result_store is None:
        return {"ok": False, "issue": "result_store.missing"}
    material_lookup = _material_by_cell(project)
    updated_stages = 0
    total_cells = 0
    yielded_cells = 0
    modes_by_stage: dict[str, dict[str, int]] = {}
    for phase_id, stage in dict(getattr(result_store, "phase_results", {}) or {}).items():
        strain_field = stage.fields.get("cell_strain")
        if strain_field is None or int(strain_field.components or 1) != 6:
            continue
        entity_ids = list(strain_field.entity_ids or [])
        values = list(strain_field.values or [])
        cell_count = len(values) // 6
        plastic: list[float] = []
        yielded: list[float] = []
        margins: list[float] = []
        multipliers: list[float] = []
        nonlinear_stress: list[float] = []
        mode_counts: dict[str, int] = {}
        for i in range(cell_count):
            cid = int(entity_ids[i]) if i < len(entity_ids) and str(entity_ids[i]).lstrip("-").isdigit() else i
            strain = np.asarray(values[6 * i : 6 * i + 6], dtype=float)
            params = _material_parameters(material_lookup.get(cid))
            model = MohrCoulomb(**params)
            state = model.update(strain, model.create_state())
            yielded_flag = bool(state.internal.get("yielded", False))
            mode = str(state.internal.get("yield_mode", "elastic"))
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            plastic.extend([float(v) for v in np.asarray(state.plastic_strain, dtype=float).reshape(6)])
            nonlinear_stress.extend([float(v) for v in np.asarray(state.stress, dtype=float).reshape(6)])
            yielded.append(1.0 if yielded_flag else 0.0)
            margins.append(float(state.internal.get("yield_margin", 0.0)))
            multipliers.append(float(state.internal.get("plastic_multiplier", 0.0)))
            total_cells += 1
            yielded_cells += int(yielded_flag)
        if cell_count <= 0:
            continue
        stage.add_field(ResultFieldRecord(name="cell_plastic_strain", stage_id=phase_id, association="cell", values=plastic, entity_ids=entity_ids[:cell_count], components=6, metadata={"components": ["ep_xx", "ep_yy", "ep_zz", "gp_xy", "gp_yz", "gp_xz"], "source": "mohr_coulomb_preview"}))
        stage.add_field(ResultFieldRecord(name="cell_mohr_coulomb_stress", stage_id=phase_id, association="cell", values=nonlinear_stress, entity_ids=entity_ids[:cell_count], components=6, metadata={"components": ["sxx", "syy", "szz", "txy", "tyz", "txz"], "source": "mohr_coulomb_preview"}))
        stage.add_field(ResultFieldRecord(name="cell_yielded", stage_id=phase_id, association="cell", values=yielded, entity_ids=entity_ids[:cell_count], components=1, metadata={"source": "mohr_coulomb_preview"}))
        stage.add_field(ResultFieldRecord(name="cell_yield_margin", stage_id=phase_id, association="cell", values=margins, entity_ids=entity_ids[:cell_count], components=1, metadata={"source": "mohr_coulomb_preview"}))
        stage.add_field(ResultFieldRecord(name="cell_plastic_multiplier", stage_id=phase_id, association="cell", values=multipliers, entity_ids=entity_ids[:cell_count], components=1, metadata={"source": "mohr_coulomb_preview"}))
        stage.metrics["yielded_cell_fraction"] = float(sum(yielded) / max(len(yielded), 1))
        stage.metrics["plastic_cell_count"] = float(sum(yielded))
        stage.metadata.setdefault("nonlinear_soil", {})["mohr_coulomb_preview"] = {"source_backend": source_backend, "mode_counts": mode_counts}
        modes_by_stage[str(phase_id)] = mode_counts
        updated_stages += 1
    report = {
        "ok": updated_stages > 0,
        "algorithm": "mohr_coulomb_preview_after_linear_global_solve",
        "engineering_level": "material_update_preview_not_full_global_newton",
        "updated_stage_count": updated_stages,
        "cell_count": total_cells,
        "yielded_cell_count": yielded_cells,
        "yielded_cell_fraction": float(yielded_cells / max(total_cells, 1)),
        "modes_by_stage": modes_by_stage,
    }
    getattr(project, "metadata", {}).setdefault("nonlinear_soil", {})["mohr_coulomb_preview"] = report
    return report


__all__ = ["apply_mohr_coulomb_state_update"]
