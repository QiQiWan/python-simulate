from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from geoai_simkit.core.model import BoundaryCondition, LoadDefinition, SimulationModel
from geoai_simkit.core.types import ResultField
from geoai_simkit.solver.base import SolverSettings
from geoai_simkit.solver.hex8_linear import (
    Hex8Submesh,
    LinearRegionMaterial,
    extract_hex8_submesh,
    solve_linear_hex8,
    subset_hex8_submesh,
)
from geoai_simkit.solver.interface_elements import assemble_interface_response
from geoai_simkit.solver.linear_algebra import configure_linear_algebra_threads
from geoai_simkit.solver.linsys import SparseBlockMatrix
from geoai_simkit.solver.operators import (
    BoundaryOperator,
    ContactOperator,
    ContinuumHex8Operator,
    ContinuumTet4Operator,
    InterfaceOperator,
    OperatorContext,
    StructuralOperator,
)
from geoai_simkit.solver.staging import StageManager
from geoai_simkit.solver.structural_elements import (
    apply_structural_loads,
    assemble_structural_stiffness,
)
from geoai_simkit.solver.tet4_linear import (
    Tet4Submesh,
    extract_tet4_submesh,
    solve_linear_tet4,
    subset_tet4_submesh,
)
from geoai_simkit.solver.warp_backend import WarpBackend


_LINEAR_MATERIAL_TYPES = {'linear_elastic', 'linear_elastic_soil'}
_HEX8_CELL_TYPES = {11, 12}
_TET4_CELL_TYPE = 10
_REFERENCE_STRUCTURAL_KINDS = {'truss2'}
_REFERENCE_INTERFACE_KINDS = {'node_pair', 'spring', 'contact_pair'}


@dataclass(slots=True)
class _StageSolveResult:
    u_local: np.ndarray
    cell_stress: np.ndarray
    cell_vm: np.ndarray
    assembly_info: dict[str, Any]
    residual_local: np.ndarray
    reaction_local: np.ndarray


@dataclass(slots=True)
class _StageIncrementResult:
    stage_name: str
    load_factor: float
    active_cell_count: int
    iteration_count: int
    total_u: np.ndarray
    cell_stress_full: np.ndarray
    cell_vm_full: np.ndarray
    assembly_info: dict[str, Any]
    status: str = 'completed'


@dataclass(slots=True)
class _ReferenceRuntimeState:
    family: str
    x0: np.ndarray
    base_submesh: Hex8Submesh | Tet4Submesh
    total_u: np.ndarray
    stage_start_total_u: np.ndarray
    stage_current_u: np.ndarray
    residual_full: np.ndarray
    reaction_full: np.ndarray
    cell_stress_full: np.ndarray
    cell_vm_full: np.ndarray
    cell_region_map: dict[int, str]
    stage_names: list[str] = field(default_factory=list)
    stage_modes: dict[str, str] = field(default_factory=dict)
    linear_assembly_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    solver_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    step_control_trace: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    active_stage_name: str | None = None


class ReferenceBackend:
    """Rebuilt staged reference solver for linear continuum cases.

    The reference path now exposes stage/increment hooks so the runtime can drive
    stage execution directly instead of wrapping one monolithic model solve.
    Advanced nonlinear/interface/structural cases still fall back to the legacy
    backend until the operator stack is rebuilt.
    """

    def __init__(self, fallback: Any | None = None) -> None:
        self.fallback = fallback or WarpBackend()

    def _cell_region_lookup(self, model: SimulationModel, cell_count: int) -> dict[int, str]:
        lookup: dict[int, str] = {}
        for region in model.region_tags:
            for cid in np.asarray(region.cell_ids, dtype=np.int64):
                lookup[int(cid)] = str(region.name)
        return lookup

    def _linear_material_from_binding(self, binding) -> LinearRegionMaterial:
        params = dict(binding.parameters)
        E = float(params.get('E') or params.get('E50ref') or params.get('Eurref') or 1.0e7)
        nu = float(params.get('nu') or params.get('nu_ur') or 0.3)
        rho = float(params.get('rho') or 0.0)
        return LinearRegionMaterial(E=E, nu=nu, rho=rho)

    def _linear_materials(
        self,
        model: SimulationModel,
        full_cell_ids: np.ndarray,
        cell_region_map: dict[int, str],
    ) -> list[LinearRegionMaterial]:
        materials: list[LinearRegionMaterial] = []
        for cid in np.asarray(full_cell_ids, dtype=np.int64):
            region_name = cell_region_map.get(int(cid), '')
            binding = model.material_for_region(region_name)
            if binding is None:
                raise KeyError(f'No material binding found for region: {region_name}')
            materials.append(self._linear_material_from_binding(binding))
        return materials

    def _structure_kind_counts(self, structures) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in structures:
            kind = str(item.kind or '').strip().lower() or 'unknown'
            counts[kind] = int(counts.get(kind, 0) + 1)
        return counts

    def _interface_kind_counts(self, interfaces) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in interfaces:
            kind = str(item.kind or '').strip().lower() or 'unknown'
            counts[kind] = int(counts.get(kind, 0) + 1)
        return counts

    def _vector_summary(self, values: np.ndarray | None, *, prefix: str) -> dict[str, float | int]:
        array = (
            np.empty((0,), dtype=float)
            if values is None
            else np.asarray(values, dtype=float).reshape(-1)
        )
        return {
            f'{prefix}_size': int(array.size),
            f'{prefix}_norm': float(np.linalg.norm(array)) if array.size else 0.0,
            f'{prefix}_max_abs': float(np.max(np.abs(array))) if array.size else 0.0,
        }

    def _coupling_support_summary(
        self,
        model: SimulationModel,
        *,
        mesh_family: str | None = None,
    ) -> dict[str, object]:
        resolved_mesh_family = (
            self._mesh_family(model)
            if mesh_family is None
            else str(mesh_family)
        )
        structure_kinds = sorted(self._structure_kind_counts(model.structures))
        interface_kinds = sorted(self._interface_kind_counts(model.interfaces))
        unsupported_structure_kinds = sorted(
            kind for kind in structure_kinds
            if kind not in _REFERENCE_STRUCTURAL_KINDS
        )
        unsupported_interface_kinds = sorted(
            kind for kind in interface_kinds
            if kind not in _REFERENCE_INTERFACE_KINDS
        )
        interface_elements_only = bool(model.interface_elements) and not bool(model.interfaces)
        supports_structures = (
            not bool(model.structures)
            or (
                resolved_mesh_family == 'hex8'
                and not unsupported_structure_kinds
            )
        )
        supports_interfaces = (
            (not bool(model.interfaces) and not interface_elements_only)
            or (
                resolved_mesh_family == 'hex8'
                and not unsupported_interface_kinds
                and not interface_elements_only
            )
        )
        return {
            'mesh_family': resolved_mesh_family,
            'structure_kinds': structure_kinds,
            'interface_kinds': interface_kinds,
            'unsupported_structure_kinds': unsupported_structure_kinds,
            'unsupported_interface_kinds': unsupported_interface_kinds,
            'supports_structures': bool(supports_structures),
            'supports_interfaces': bool(supports_interfaces),
            'interface_elements_only': bool(interface_elements_only),
        }

    def _evaluate_boundary_operator(
        self,
        *,
        stage_name: str,
        load_factor: float,
        bcs,
        loads,
        stage_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        contribution = BoundaryOperator().evaluate(
            {
                'boundary_condition_count': int(len(tuple(bcs))),
                'load_count': int(len(tuple(loads))),
                'boundary_condition_kinds': sorted(
                    {
                        str(item.kind).strip().lower()
                        for item in tuple(bcs)
                        if str(item.kind).strip()
                    }
                ),
                'load_kinds': sorted(
                    {
                        str(item.kind).strip().lower()
                        for item in tuple(loads)
                        if str(item.kind).strip()
                    }
                ),
                'active_support_groups': list(
                    dict(stage_metadata or {}).get('active_support_groups', []) or []
                ),
                'active_interface_groups': list(
                    dict(stage_metadata or {}).get('active_interface_groups', []) or []
                ),
            },
            OperatorContext(
                stage_name=stage_name,
                partition_id=None,
                load_factor=float(load_factor),
                metadata=dict(stage_metadata or {}),
            ),
        )
        return dict(contribution.diagnostics or {})

    def _evaluate_structural_operator(
        self,
        *,
        stage_name: str,
        load_factor: float,
        structures,
        submesh: Hex8Submesh,
        assembly_result,
        stage_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        matrix_summary = SparseBlockMatrix.from_matrix(
            assembly_result.K,
            block_size=3,
            metadata={
                'storage': 'dense',
                'backend': 'reference-structural-overlay',
                'device': 'cpu',
            },
        ).summary()
        dof_map = assembly_result.dof_map
        contribution = StructuralOperator().evaluate(
            {
                'count': int(assembly_result.count),
                'warnings': list(assembly_result.warnings),
                'kind_counts': self._structure_kind_counts(structures),
                'supported_on_reference_path': True,
                'translational_only': bool(
                    int(dof_map.total_ndof) == int(dof_map.trans_ndof)
                ),
                'active_point_count': int(
                    len(
                        {
                            int(gid)
                            for item in structures
                            for gid in tuple(item.point_ids)
                            if int(gid) in submesh.local_by_global
                        }
                    )
                ),
                'dof_summary': {
                    'translational_dof_count': int(dof_map.trans_ndof),
                    'rotational_dof_count': int(dof_map.total_ndof - dof_map.trans_ndof),
                    'total_dof_count': int(dof_map.total_ndof),
                },
                'load_summary': self._vector_summary(
                    np.asarray(assembly_result.F, dtype=float),
                    prefix='external_force',
                ),
                'linear_system_summary': {
                    **matrix_summary,
                    **self._vector_summary(
                        np.asarray(assembly_result.F, dtype=float),
                        prefix='rhs',
                    ),
                    'block_size': 3,
                },
            },
            OperatorContext(
                stage_name=stage_name,
                partition_id=None,
                load_factor=float(load_factor),
                metadata=dict(stage_metadata or {}),
            ),
        )
        return dict(contribution.diagnostics or {})

    def _evaluate_interface_operator(
        self,
        *,
        stage_name: str,
        load_factor: float,
        interfaces,
        assembly_result,
        interface_states: dict[str, list[object]],
        stage_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state_rows = [
            state
            for rows in dict(interface_states or {}).values()
            for state in list(rows or [])
        ]
        traction_norm_sum = float(
            sum(
                np.linalg.norm(np.asarray(getattr(item, 'traction', np.zeros(3)), dtype=float))
                for item in state_rows
            )
        )
        traction_max_abs = float(
            max(
                [
                    float(
                        np.max(
                            np.abs(
                                np.asarray(
                                    getattr(item, 'traction', np.zeros(3)),
                                    dtype=float,
                                )
                            )
                        )
                    )
                    for item in state_rows
                ],
                default=0.0,
            )
        )
        matrix_summary = SparseBlockMatrix.from_matrix(
            assembly_result.K,
            block_size=3,
            metadata={
                'storage': 'dense',
                'backend': 'reference-interface-overlay',
                'device': 'cpu',
            },
        ).summary()
        contribution = InterfaceOperator().evaluate(
            {
                'count': int(assembly_result.count),
                'warnings': list(assembly_result.warnings),
                'kind_counts': self._interface_kind_counts(interfaces),
                'supported_on_reference_path': True,
                'closed_pair_count': int(
                    sum(bool(getattr(item, 'closed', False)) for item in state_rows)
                ),
                'open_pair_count': int(
                    sum(not bool(getattr(item, 'closed', False)) for item in state_rows)
                ),
                'internal_force_summary': self._vector_summary(
                    np.asarray(assembly_result.Fint, dtype=float),
                    prefix='internal_force',
                ),
                'traction_summary': {
                    'traction_norm_sum': traction_norm_sum,
                    'traction_max_abs': traction_max_abs,
                },
                'linear_system_summary': {
                    **matrix_summary,
                    **self._vector_summary(
                        np.asarray(assembly_result.Fint, dtype=float),
                        prefix='rhs',
                    ),
                    'rhs_role': 'internal_force',
                    'block_size': 3,
                },
            },
            OperatorContext(
                stage_name=stage_name,
                partition_id=None,
                load_factor=float(load_factor),
                metadata=dict(stage_metadata or {}),
            ),
        )
        return dict(contribution.diagnostics or {})

    def _evaluate_contact_operator(
        self,
        *,
        stage_name: str,
        load_factor: float,
        interface_summary: dict[str, Any],
        stage_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        contribution = ContactOperator().evaluate(
            {
                'implemented_via_interface_operator': True,
                'count': int(interface_summary.get('active_interface_count', 0) or 0),
                'closed_pair_count': int(interface_summary.get('closed_pair_count', 0) or 0),
                'open_pair_count': int(interface_summary.get('open_pair_count', 0) or 0),
                'warnings': list(interface_summary.get('warnings', []) or []),
                'coupling_model': 'node-pair-penalty-contact',
                'friction_model': 'coulomb-penalty',
            },
            OperatorContext(
                stage_name=stage_name,
                partition_id=None,
                load_factor=float(load_factor),
                metadata=dict(stage_metadata or {}),
            ),
        )
        return dict(contribution.diagnostics or {})

    def _build_hex8_auxiliary_system(
        self,
        *,
        model: SimulationModel,
        stage_name: str,
        submesh: Hex8Submesh,
        stage_loads,
        load_factor: float,
        current_u_nodes: np.ndarray,
        stage_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        extra_stiffness = None
        extra_rhs = np.zeros((submesh.points.shape[0] * 3,), dtype=float)
        has_rhs = False
        operator_summaries: dict[str, dict[str, Any]] = {}

        structures = model.structures_for_stage(stage_name)
        if structures:
            structural_asm = assemble_structural_stiffness(structures, submesh)
            if int(structural_asm.dof_map.total_ndof) != int(structural_asm.dof_map.trans_ndof):
                raise ValueError(
                    'rotational structural DOFs are not supported on the rebuilt Hex8 reference path yet'
                )
            apply_structural_loads(
                structural_asm.F,
                submesh,
                structural_asm.dof_map,
                tuple(stage_loads),
            )
            structural_asm.F *= float(load_factor)
            extra_stiffness = np.asarray(structural_asm.K, dtype=float).copy()
            extra_rhs += np.asarray(structural_asm.F, dtype=float).reshape(-1)
            has_rhs = True
            operator_summaries['structural'] = self._evaluate_structural_operator(
                stage_name=stage_name,
                load_factor=float(load_factor),
                structures=structures,
                submesh=submesh,
                assembly_result=structural_asm,
                stage_metadata=stage_metadata,
            )

        interfaces = model.interfaces_for_stage(stage_name)
        if interfaces:
            interface_asm, interface_states = assemble_interface_response(
                interfaces,
                submesh,
                np.asarray(current_u_nodes, dtype=float),
            )
            interface_matrix = np.asarray(interface_asm.K, dtype=float)
            extra_stiffness = (
                interface_matrix.copy()
                if extra_stiffness is None
                else (np.asarray(extra_stiffness, dtype=float) + interface_matrix)
            )
            extra_rhs -= np.asarray(interface_asm.Fint, dtype=float).reshape(-1)
            has_rhs = True
            operator_summaries['interface'] = self._evaluate_interface_operator(
                stage_name=stage_name,
                load_factor=float(load_factor),
                interfaces=interfaces,
                assembly_result=interface_asm,
                interface_states=interface_states,
                stage_metadata=stage_metadata,
            )
            operator_summaries['contact'] = self._evaluate_contact_operator(
                stage_name=stage_name,
                load_factor=float(load_factor),
                interface_summary=operator_summaries['interface'],
                stage_metadata=stage_metadata,
            )

        return {
            'extra_stiffness': extra_stiffness,
            'extra_rhs': (extra_rhs if (extra_stiffness is not None or has_rhs) else None),
            'operator_summaries': operator_summaries,
        }

    def _supported_linear_continuum(self, model: SimulationModel) -> tuple[bool, str]:
        mesh_family = self._mesh_family(model)
        coupling_support = self._coupling_support_summary(
            model,
            mesh_family=mesh_family,
        )
        if bool(model.structures) and mesh_family != 'hex8':
            return False, 'Tet4 structural overlays are not on the rebuilt reference path yet'
        if bool(model.interfaces) and mesh_family != 'hex8':
            return False, 'Tet4 interface/contact coupling is not on the rebuilt reference path yet'
        if coupling_support['unsupported_structure_kinds']:
            return (
                False,
                'unsupported structural kinds require fallback: '
                f"{list(coupling_support['unsupported_structure_kinds'])}",
            )
        if coupling_support['unsupported_interface_kinds']:
            return (
                False,
                'unsupported interface kinds require fallback: '
                f"{list(coupling_support['unsupported_interface_kinds'])}",
            )
        if bool(coupling_support['interface_elements_only']):
            return False, 'explicit interface elements without raw node-pair interfaces are not on the rebuilt reference path yet'
        unsupported = [
            binding.material_name
            for binding in model.materials
            if str(binding.material_name).strip().lower() not in _LINEAR_MATERIAL_TYPES
        ]
        if unsupported:
            return False, f'nonlinear or unsupported material models require fallback: {sorted(set(unsupported))}'
        return True, ''

    def _mesh_family(self, model: SimulationModel) -> str:
        grid = model.to_unstructured_grid()
        celltypes = {int(item) for item in np.asarray(getattr(grid, 'celltypes', []), dtype=np.int32).tolist()}
        if celltypes and celltypes.issubset(_HEX8_CELL_TYPES):
            return 'hex8'
        if celltypes == {_TET4_CELL_TYPE}:
            return 'tet4'
        return 'mixed'

    def _scale_boundary_conditions(
        self,
        bcs: Iterable[BoundaryCondition],
        factor: float,
    ) -> tuple[BoundaryCondition, ...]:
        scaled: list[BoundaryCondition] = []
        for bc in bcs:
            bc_factor = 1.0 if bc.metadata.get('scale_with_increment', True) is False else float(factor)
            scaled.append(
                BoundaryCondition(
                    name=bc.name,
                    kind=bc.kind,
                    target=bc.target,
                    components=tuple(int(comp) for comp in bc.components),
                    values=tuple(float(value) * bc_factor for value in bc.values),
                    metadata=dict(bc.metadata),
                )
            )
        return tuple(scaled)

    def _scale_loads(
        self,
        loads: Iterable[LoadDefinition],
        factor: float,
    ) -> tuple[LoadDefinition, ...]:
        scaled: list[LoadDefinition] = []
        for load in loads:
            load_factor = 1.0 if load.metadata.get('scale_with_increment', True) is False else float(factor)
            scaled.append(
                LoadDefinition(
                    name=load.name,
                    kind=load.kind,
                    target=load.target,
                    values=tuple(float(value) * load_factor for value in load.values),
                    metadata=dict(load.metadata),
                )
            )
        return tuple(scaled)

    def _stage_partition_activity_summary(self, stage_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = dict(stage_metadata or {})
        partition_activity = dict(metadata.get('partition_activity', {}) or {})
        if not partition_activity:
            return {}
        return {
            'active_partition_count': int(partition_activity.get('active_partition_count', 0) or 0),
            'stage_locality_ratio': float(partition_activity.get('stage_locality_ratio', 0.0) or 0.0),
            'active_partition_balance_ratio': float(partition_activity.get('active_partition_balance_ratio', 1.0) or 1.0),
            'active_node_balance_ratio': float(partition_activity.get('active_node_balance_ratio', 1.0) or 1.0),
            'idle_partition_ids': list(partition_activity.get('idle_partition_ids', []) or []),
            'active_cells_per_partition': list(partition_activity.get('active_cells_per_partition', []) or []),
            'active_gp_states_per_partition': list(partition_activity.get('active_gp_states_per_partition', []) or []),
            'active_owned_nodes_per_partition': list(partition_activity.get('active_owned_nodes_per_partition', []) or []),
            'active_owned_dofs_per_partition': list(partition_activity.get('active_owned_dofs_per_partition', []) or []),
        }

    def _partition_linear_system_summaries(
        self,
        stage_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        metadata = dict(stage_metadata or {})
        stage_linear_system_plan = dict(metadata.get('stage_linear_system_plan', {}) or {})
        if stage_linear_system_plan.get('partition_local_systems'):
            return [
                {
                    **dict(item),
                    'summary_source': 'compile-stage-plan',
                    'matrix_summary_kind': 'estimated-local-partition',
                    'has_actual_local_matrix': False,
                }
                for item in stage_linear_system_plan.get('partition_local_systems', []) or []
            ]
        partition_activity = dict(metadata.get('partition_activity', {}) or {})
        partition_layout = list(metadata.get('partition_layout', []) or [])
        linear_system_estimates = list(metadata.get('linear_system_partition_estimates', []) or [])
        estimate_by_partition = {
            int(item.get('partition_id', index)): dict(item)
            for index, item in enumerate(linear_system_estimates)
        }
        active_cells_per_partition = list(partition_activity.get('active_cells_per_partition', []) or [])
        active_gp_states_per_partition = list(partition_activity.get('active_gp_states_per_partition', []) or [])
        active_owned_nodes_per_partition = list(partition_activity.get('active_owned_nodes_per_partition', []) or [])
        active_owned_dofs_per_partition = list(partition_activity.get('active_owned_dofs_per_partition', []) or [])
        rows: list[dict[str, Any]] = []
        for index, layout in enumerate(partition_layout):
            layout_row = dict(layout)
            partition_id = int(layout_row.get('partition_id', index) or index)
            estimate_row = dict(estimate_by_partition.get(partition_id, {}))
            owned_cell_count = int(layout_row.get('owned_cell_count', estimate_row.get('owned_cell_count', 0)) or 0)
            owned_dof_count = int(layout_row.get('owned_dof_count', estimate_row.get('owned_dof_count', 0)) or 0)
            local_dof_count = int(layout_row.get('local_dof_count', estimate_row.get('local_dof_count', 0)) or 0)
            active_cell_count = int(active_cells_per_partition[index]) if index < len(active_cells_per_partition) else 0
            active_gp_state_count = (
                int(active_gp_states_per_partition[index])
                if index < len(active_gp_states_per_partition)
                else 0
            )
            active_owned_node_count = (
                int(active_owned_nodes_per_partition[index])
                if index < len(active_owned_nodes_per_partition)
                else 0
            )
            active_owned_dof_count = (
                int(active_owned_dofs_per_partition[index])
                if index < len(active_owned_dofs_per_partition)
                else 0
            )
            cell_ratio = float(active_cell_count / max(1, owned_cell_count)) if owned_cell_count > 0 else 0.0
            dof_ratio = float(active_owned_dof_count / max(1, owned_dof_count)) if owned_dof_count > 0 else 0.0
            activity_ratio = float(max(0.0, min(1.0, max(cell_ratio, dof_ratio))))
            estimated_nnz_entries = int(round(float(estimate_row.get('matrix_nnz_entries', 0) or 0) * activity_ratio))
            estimated_nnz_blocks = int(round(float(estimate_row.get('matrix_nnz_blocks', 0) or 0) * activity_ratio))
            estimated_storage_bytes = int(round(float(estimate_row.get('matrix_storage_bytes', 0) or 0) * activity_ratio))
            rows.append(
                {
                    'partition_id': partition_id,
                    'active': bool(active_cell_count > 0),
                    'activity_ratio': float(activity_ratio),
                    'active_cell_count': int(active_cell_count),
                    'active_gp_state_count': int(active_gp_state_count),
                    'active_owned_node_count': int(active_owned_node_count),
                    'active_owned_dof_count': int(active_owned_dof_count),
                    'owned_cell_count': int(owned_cell_count),
                    'owned_node_count': int(layout_row.get('owned_node_count', estimate_row.get('owned_node_count', 0)) or 0),
                    'ghost_node_count': int(layout_row.get('ghost_node_count', estimate_row.get('ghost_node_count', 0)) or 0),
                    'owned_dof_count': int(owned_dof_count),
                    'ghost_dof_count': int(layout_row.get('ghost_dof_count', estimate_row.get('ghost_dof_count', 0)) or 0),
                    'local_dof_count': int(local_dof_count),
                    'matrix_shape': list(estimate_row.get('matrix_shape', [local_dof_count, local_dof_count]) or [local_dof_count, local_dof_count]),
                    'matrix_nnz_entries_estimate': int(estimated_nnz_entries),
                    'matrix_nnz_blocks_estimate': int(estimated_nnz_blocks),
                    'matrix_storage_bytes_estimate': int(estimated_storage_bytes),
                    'summary_source': 'runtime-stage-activity-estimate',
                    'matrix_summary_kind': 'estimated-local-partition',
                    'has_actual_local_matrix': False,
                }
            )
        return rows

    def _evaluate_continuum_operator(
        self,
        *,
        family: str,
        stage_name: str,
        load_factor: float,
        submesh: Hex8Submesh | Tet4Submesh | None,
        assembly_info: dict[str, Any],
        stage_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        operator = ContinuumHex8Operator() if family == 'hex8' else ContinuumTet4Operator()
        partition_linear_systems = [
            dict(item)
            for item in dict(assembly_info).get('partition_linear_systems', []) or []
        ]
        if not partition_linear_systems:
            partition_linear_systems = self._partition_linear_system_summaries(stage_metadata)
        contribution = operator.evaluate(
            {
                'assembly_info': dict(assembly_info),
                'linear_system_summary': dict(assembly_info.get('linear_system_summary', {}) or {}),
                'partition_linear_systems': partition_linear_systems,
                'active_cell_count': 0 if submesh is None else int(np.asarray(submesh.full_cell_ids, dtype=np.int64).size),
                'active_node_count': 0 if submesh is None else int(np.asarray(submesh.global_point_ids, dtype=np.int64).size),
                'gauss_points_per_cell': 8 if family == 'hex8' else 1,
            },
            OperatorContext(
                stage_name=stage_name,
                partition_id=None,
                load_factor=float(load_factor),
                metadata=dict(stage_metadata or {}),
            ),
        )
        diagnostics = dict(contribution.diagnostics or {})
        diagnostics['partition_local_systems'] = partition_linear_systems
        diagnostics['partition_local_system_sources'] = sorted(
            {
                str(item.get('summary_source', 'unknown'))
                for item in partition_linear_systems
            }
        )
        return diagnostics

    def _solve_hex8_stage(
        self,
        model: SimulationModel,
        stage_name: str,
        submesh: Hex8Submesh,
        stage_bcs,
        stage_loads,
        settings: SolverSettings,
        *,
        solver_metadata: dict[str, Any],
        cell_region_map: dict[int, str],
        auxiliary_system: dict[str, Any] | None = None,
    ) -> _StageSolveResult:
        materials = self._linear_materials(model, submesh.full_cell_ids, cell_region_map)
        u_local, cell_stress, cell_vm, assembly_info, residual_local, reaction_local = solve_linear_hex8(
            submesh,
            materials,
            bcs=stage_bcs,
            loads=stage_loads,
            gravity=settings.gravity,
            displacement_scale=1.0,
            prefer_sparse=bool(settings.prefer_sparse),
            thread_count=int(settings.thread_count),
            compute_device='cpu',
            solver_metadata=solver_metadata,
            extra_stiffness=(
                None
                if auxiliary_system is None
                else auxiliary_system.get('extra_stiffness')
            ),
            extra_rhs=(
                None
                if auxiliary_system is None
                else auxiliary_system.get('extra_rhs')
            ),
            auxiliary_system_summaries=(
                {}
                if auxiliary_system is None
                else dict(auxiliary_system.get('operator_summaries', {}) or {})
            ),
        )
        assembly_info = dict(assembly_info)
        assembly_info['stage_name'] = stage_name
        assembly_info['solver_path'] = 'reference'
        if auxiliary_system is not None:
            assembly_info['auxiliary_operator_summaries'] = {
                str(name): dict(summary)
                for name, summary in dict(
                    auxiliary_system.get('operator_summaries', {}) or {}
                ).items()
            }
        return _StageSolveResult(
            u_local=u_local,
            cell_stress=cell_stress,
            cell_vm=cell_vm,
            assembly_info=assembly_info,
            residual_local=residual_local,
            reaction_local=reaction_local,
        )

    def _solve_tet4_stage(
        self,
        model: SimulationModel,
        stage_name: str,
        submesh: Tet4Submesh,
        stage_bcs,
        stage_loads,
        settings: SolverSettings,
        *,
        solver_metadata: dict[str, Any],
        cell_region_map: dict[int, str],
    ) -> _StageSolveResult:
        materials = self._linear_materials(model, submesh.full_cell_ids, cell_region_map)
        u_local, cell_stress, cell_vm, assembly_info, residual_local, reaction_local = solve_linear_tet4(
            submesh,
            materials,
            bcs=stage_bcs,
            loads=stage_loads,
            gravity=settings.gravity,
            displacement_scale=1.0,
            prefer_sparse=bool(settings.prefer_sparse),
            thread_count=int(settings.thread_count),
            compute_device='cpu',
            solver_metadata=solver_metadata,
        )
        assembly_info = dict(assembly_info)
        assembly_info['stage_name'] = stage_name
        assembly_info['solver_path'] = 'reference'
        return _StageSolveResult(
            u_local=u_local,
            cell_stress=cell_stress,
            cell_vm=cell_vm,
            assembly_info=assembly_info,
            residual_local=residual_local,
            reaction_local=reaction_local,
        )

    def _fallback(self, model: SimulationModel, settings: SolverSettings, reason: str) -> SimulationModel:
        solved = self.fallback.solve(model, settings)
        warnings = list(solved.metadata.get('solver_warnings', []) or [])
        warnings.append(f'Reference backend fallback: {reason}.')
        solved.metadata['solver_warnings'] = warnings
        solved.metadata['stage_execution_diagnostics'] = self.stage_execution_diagnostics(model, settings)
        solved.metadata.setdefault('solver_backend_chain', [])
        solved.metadata['solver_backend_chain'] = [
            *list(solved.metadata.get('solver_backend_chain', []) or []),
            'reference-fallback->warp',
        ]
        return solved

    def stage_execution_diagnostics(self, model: SimulationModel, settings: SolverSettings) -> dict[str, object]:
        forced_legacy = str(settings.metadata.get('solver_backend') or '').strip().lower() == 'legacy-warp'
        mesh_family = self._mesh_family(model)
        coupling_support = self._coupling_support_summary(
            model,
            mesh_family=mesh_family,
        )
        supported_continuum, support_reason = self._supported_linear_continuum(model)
        stage_execution_supported = bool(
            not forced_legacy
            and supported_continuum
            and mesh_family in {'hex8', 'tet4'}
        )
        reasons: list[str] = []
        if forced_legacy:
            reasons.append('settings requested the legacy warp backend')
        if support_reason:
            reasons.append(str(support_reason))
        if mesh_family not in {'hex8', 'tet4'}:
            reasons.append(f'mesh family {mesh_family!r} is not on the rebuilt reference path yet')
        if not reasons:
            reasons.append('The case is eligible for the rebuilt linear continuum stage runtime.')
        return {
            'backend': 'reference-linear-stage-runtime',
            'supported': bool(stage_execution_supported),
            'mesh_family': str(mesh_family),
            'forced_legacy_backend': bool(forced_legacy),
            'structure_count': int(len(model.structures)),
            'interface_count': int(len(model.interfaces)),
            'interface_element_count': int(len(model.interface_elements)),
            'structure_kinds': list(coupling_support.get('structure_kinds', []) or []),
            'interface_kinds': list(coupling_support.get('interface_kinds', []) or []),
            'unsupported_structure_kinds': list(
                coupling_support.get('unsupported_structure_kinds', []) or []
            ),
            'unsupported_interface_kinds': list(
                coupling_support.get('unsupported_interface_kinds', []) or []
            ),
            'supports_structures': bool(
                coupling_support.get('supports_structures', False)
            ),
            'supports_interfaces': bool(
                coupling_support.get('supports_interfaces', False)
            ),
            'interface_elements_only': bool(
                coupling_support.get('interface_elements_only', False)
            ),
            'material_models': sorted(
                {
                    str(binding.material_name).strip().lower()
                    for binding in model.materials
                }
            ),
            'reasons': reasons,
        }

    def supports_stage_execution(self, model: SimulationModel, settings: SolverSettings) -> bool:
        return bool(self.stage_execution_diagnostics(model, settings).get('supported', False))

    def initialize_runtime_state(self, model: SimulationModel, settings: SolverSettings) -> _ReferenceRuntimeState:
        if not self.supports_stage_execution(model, settings):
            raise ValueError('Reference runtime state requested for an unsupported model.')
        model.ensure_regions()
        settings.thread_count = int(configure_linear_algebra_threads(int(settings.thread_count)))
        model.clear_results()
        grid = model.to_unstructured_grid()
        x0 = np.asarray(grid.points, dtype=float).copy()
        family = self._mesh_family(model)
        if family == 'hex8':
            base_submesh = extract_hex8_submesh(grid)
            if base_submesh.elements.size == 0:
                raise ValueError('Hex8 mesh extraction returned no supported cells.')
        else:
            base_submesh = extract_tet4_submesh(grid)
            if base_submesh.elements.size == 0:
                raise ValueError('Tet4 mesh extraction returned no supported cells.')
        return _ReferenceRuntimeState(
            family=family,
            x0=x0,
            base_submesh=base_submesh,
            total_u=np.zeros((grid.n_points, 3), dtype=float),
            stage_start_total_u=np.zeros((grid.n_points, 3), dtype=float),
            stage_current_u=np.zeros((grid.n_points, 3), dtype=float),
            residual_full=np.zeros((grid.n_points, 3), dtype=float),
            reaction_full=np.zeros((grid.n_points, 3), dtype=float),
            cell_stress_full=np.zeros((grid.n_cells, 6), dtype=float),
            cell_vm_full=np.zeros(grid.n_cells, dtype=float),
            cell_region_map=self._cell_region_lookup(model, int(grid.n_cells)),
        )

    def begin_stage(self, runtime_state: _ReferenceRuntimeState, *, stage_name: str) -> None:
        runtime_state.active_stage_name = stage_name
        runtime_state.stage_start_total_u = runtime_state.total_u.copy()
        runtime_state.stage_current_u = np.zeros_like(runtime_state.total_u)
        runtime_state.residual_full = np.zeros_like(runtime_state.total_u)
        runtime_state.reaction_full = np.zeros_like(runtime_state.total_u)

    def advance_stage_increment(
        self,
        model: SimulationModel,
        settings: SolverSettings,
        runtime_state: _ReferenceRuntimeState,
        *,
        stage_name: str,
        active_regions: Iterable[str],
        bcs,
        loads,
        load_factor: float,
        increment_index: int,
        increment_count: int,
        stage_metadata: dict[str, Any] | None = None,
    ) -> _StageIncrementResult:
        active_region_set = {str(name) for name in active_regions if str(name)}
        base_submesh = runtime_state.base_submesh
        active_mask = np.array(
            [
                runtime_state.cell_region_map.get(int(cid), None) in active_region_set
                for cid in np.asarray(base_submesh.full_cell_ids, dtype=np.int64)
            ],
            dtype=bool,
        )

        if not np.any(active_mask):
            runtime_state.stage_current_u = np.zeros_like(runtime_state.total_u)
            runtime_state.total_u = runtime_state.stage_start_total_u.copy()
            runtime_state.residual_full = np.zeros_like(runtime_state.total_u)
            runtime_state.reaction_full = np.zeros_like(runtime_state.total_u)
            runtime_state.cell_stress_full = np.zeros_like(runtime_state.cell_stress_full)
            runtime_state.cell_vm_full = np.zeros_like(runtime_state.cell_vm_full)
            family_label = 'Hex8' if runtime_state.family == 'hex8' else 'Tet4'
            note = f"Stage '{stage_name}' had no active {family_label} cells; inherited previous displacement state."
            if note not in runtime_state.notes:
                runtime_state.notes.append(note)
            assembly_info = {
                'stage_name': stage_name,
                'solver_path': 'reference',
                'status': 'skipped-no-active-cells',
                'increment_index': int(increment_index),
                'increment_count': int(increment_count),
                'mesh_family': runtime_state.family,
                'active_node_count': 0,
                'active_dof_count': 0,
                'active_node_ratio': 0.0,
                'active_dof_ratio': 0.0,
                **self._stage_partition_activity_summary(stage_metadata),
            }
            assembly_info['partition_linear_systems'] = self._partition_linear_system_summaries(stage_metadata)
            continuum_summary = self._evaluate_continuum_operator(
                family=runtime_state.family,
                stage_name=stage_name,
                load_factor=float(load_factor),
                submesh=None,
                assembly_info=assembly_info,
                stage_metadata=stage_metadata,
            )
            boundary_summary = self._evaluate_boundary_operator(
                stage_name=stage_name,
                load_factor=float(load_factor),
                bcs=tuple(bcs),
                loads=tuple(loads),
                stage_metadata=stage_metadata,
            )
            assembly_info['operator_summary'] = {
                **dict(continuum_summary),
                'continuum': dict(continuum_summary),
                'boundary': dict(boundary_summary),
                'linear_system_role': 'total-assembled-system',
                'active_structure_count': 0,
                'active_interface_count': 0,
                'active_contact_pair_count': 0,
                'auxiliary_operator_names': [],
                'boundary_condition_count': int(
                    boundary_summary.get('boundary_condition_count', 0) or 0
                ),
                'load_count': int(boundary_summary.get('load_count', 0) or 0),
            }
            return _StageIncrementResult(
                stage_name=stage_name,
                load_factor=float(load_factor),
                active_cell_count=0,
                iteration_count=0,
                total_u=runtime_state.total_u.copy(),
                cell_stress_full=runtime_state.cell_stress_full.copy(),
                cell_vm_full=runtime_state.cell_vm_full.copy(),
                assembly_info=assembly_info,
                status='skipped-no-active-cells',
            )

        solver_metadata = dict(settings.metadata)
        solver_metadata.update(dict(stage_metadata or {}))
        solver_metadata.update(
            {
                'load_factor': float(load_factor),
                'increment_index': int(increment_index),
                'increment_count': int(increment_count),
            }
        )
        stage_bcs = self._scale_boundary_conditions(tuple(bcs), load_factor)
        stage_loads = self._scale_loads(tuple(loads), load_factor)
        boundary_summary = self._evaluate_boundary_operator(
            stage_name=stage_name,
            load_factor=float(load_factor),
            bcs=tuple(stage_bcs),
            loads=tuple(stage_loads),
            stage_metadata=stage_metadata,
        )

        if runtime_state.family == 'hex8':
            submesh = subset_hex8_submesh(base_submesh, active_mask)
            auxiliary_system = self._build_hex8_auxiliary_system(
                model=model,
                stage_name=stage_name,
                submesh=submesh,
                stage_loads=tuple(stage_loads),
                load_factor=float(load_factor),
                current_u_nodes=np.asarray(
                    runtime_state.stage_start_total_u[submesh.global_point_ids],
                    dtype=float,
                ),
                stage_metadata=stage_metadata,
            )
            stage_result = self._solve_hex8_stage(
                model,
                stage_name,
                submesh,
                stage_bcs,
                stage_loads,
                settings,
                solver_metadata=solver_metadata,
                cell_region_map=runtime_state.cell_region_map,
                auxiliary_system=auxiliary_system,
            )
        else:
            submesh = subset_tet4_submesh(base_submesh, active_mask)
            stage_result = self._solve_tet4_stage(
                model,
                stage_name,
                submesh,
                stage_bcs,
                stage_loads,
                settings,
                solver_metadata=solver_metadata,
                cell_region_map=runtime_state.cell_region_map,
            )

        stage_delta = np.zeros_like(runtime_state.total_u)
        stage_delta[submesh.global_point_ids] = stage_result.u_local
        runtime_state.stage_current_u = stage_delta
        runtime_state.total_u = runtime_state.stage_start_total_u + stage_delta
        runtime_state.residual_full = np.zeros_like(runtime_state.total_u)
        runtime_state.reaction_full = np.zeros_like(runtime_state.total_u)
        runtime_state.residual_full[submesh.global_point_ids] = stage_result.residual_local
        runtime_state.reaction_full[submesh.global_point_ids] = stage_result.reaction_local

        runtime_state.cell_stress_full = np.zeros_like(runtime_state.cell_stress_full)
        runtime_state.cell_vm_full = np.zeros_like(runtime_state.cell_vm_full)
        runtime_state.cell_stress_full[submesh.full_cell_ids] = stage_result.cell_stress
        runtime_state.cell_vm_full[submesh.full_cell_ids] = stage_result.cell_vm

        assembly_info = dict(stage_result.assembly_info)
        assembly_info['increment_index'] = int(increment_index)
        assembly_info['increment_count'] = int(increment_count)
        assembly_info['load_factor'] = float(load_factor)
        active_node_count = int(np.asarray(submesh.global_point_ids, dtype=np.int64).size)
        global_node_count = max(1, int(runtime_state.x0.shape[0]))
        assembly_info.update(
            {
                'mesh_family': runtime_state.family,
                'active_node_count': active_node_count,
                'active_dof_count': int(active_node_count * 3),
                'active_node_ratio': float(active_node_count / global_node_count),
                'active_dof_ratio': float((active_node_count * 3) / max(1, global_node_count * 3)),
            }
        )
        assembly_info.update(self._stage_partition_activity_summary(stage_metadata))
        assembly_info['partition_linear_systems'] = [
            dict(item)
            for item in assembly_info.get('actual_partition_linear_systems', []) or []
        ]
        if not assembly_info['partition_linear_systems']:
            assembly_info['partition_linear_systems'] = self._partition_linear_system_summaries(stage_metadata)
        continuum_summary = self._evaluate_continuum_operator(
            family=runtime_state.family,
            stage_name=stage_name,
            load_factor=float(load_factor),
            submesh=submesh,
            assembly_info=assembly_info,
            stage_metadata=stage_metadata,
        )
        auxiliary_operator_summaries = {
            str(name): dict(summary)
            for name, summary in dict(
                assembly_info.get('auxiliary_operator_summaries', {}) or {}
            ).items()
        }
        assembly_info['operator_summary'] = {
            **dict(continuum_summary),
            'continuum': dict(continuum_summary),
            'boundary': dict(boundary_summary),
            **auxiliary_operator_summaries,
            'linear_system_role': 'total-assembled-system',
            'active_structure_count': int(
                auxiliary_operator_summaries.get('structural', {}).get(
                    'active_structure_count',
                    0,
                )
                or 0
            ),
            'active_interface_count': int(
                auxiliary_operator_summaries.get('interface', {}).get(
                    'active_interface_count',
                    0,
                )
                or 0
            ),
            'active_contact_pair_count': int(
                auxiliary_operator_summaries.get('contact', {}).get(
                    'active_contact_pair_count',
                    0,
                )
                or 0
            ),
            'auxiliary_operator_names': sorted(auxiliary_operator_summaries),
            'boundary_condition_count': int(
                boundary_summary.get('boundary_condition_count', 0) or 0
            ),
            'load_count': int(boundary_summary.get('load_count', 0) or 0),
        }
        return _StageIncrementResult(
            stage_name=stage_name,
            load_factor=float(load_factor),
            active_cell_count=int(np.count_nonzero(active_mask)),
            iteration_count=1,
            total_u=runtime_state.total_u.copy(),
            cell_stress_full=runtime_state.cell_stress_full.copy(),
            cell_vm_full=runtime_state.cell_vm_full.copy(),
            assembly_info=assembly_info,
            status='completed',
        )

    def commit_stage(
        self,
        model: SimulationModel,
        runtime_state: _ReferenceRuntimeState,
        *,
        stage_name: str,
        increment_result: _StageIncrementResult,
        history_rows: list[dict[str, Any]] | None = None,
        step_trace_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if stage_name not in runtime_state.stage_names:
            runtime_state.stage_names.append(stage_name)
        runtime_state.stage_modes[stage_name] = (
            'linear-reference'
            if increment_result.status == 'completed'
            else f'linear-reference:{increment_result.status}'
        )
        runtime_state.linear_assembly_meta[stage_name] = dict(increment_result.assembly_info)
        if history_rows is not None:
            runtime_state.solver_history[stage_name] = [dict(row) for row in history_rows]
        if step_trace_rows is not None:
            runtime_state.step_control_trace[stage_name] = [dict(row) for row in step_trace_rows]

        stage_increment_u = np.asarray(runtime_state.stage_current_u, dtype=float).copy()
        stage_residual = np.asarray(runtime_state.residual_full, dtype=float).copy()
        stage_reaction = np.asarray(runtime_state.reaction_full, dtype=float).copy()
        model.add_result(
            ResultField(
                name='U',
                association='point',
                values=increment_result.total_u.copy(),
                components=3,
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='U_mag',
                association='point',
                values=np.linalg.norm(increment_result.total_u, axis=1),
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='dU',
                association='point',
                values=stage_increment_u,
                components=3,
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='dU_mag',
                association='point',
                values=np.linalg.norm(stage_increment_u, axis=1),
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='residual',
                association='point',
                values=stage_residual,
                components=3,
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='residual_mag',
                association='point',
                values=np.linalg.norm(stage_residual, axis=1),
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='reaction',
                association='point',
                values=stage_reaction,
                components=3,
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='reaction_mag',
                association='point',
                values=np.linalg.norm(stage_reaction, axis=1),
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='stress',
                association='cell',
                values=increment_result.cell_stress_full.copy(),
                components=6,
                stage=stage_name,
            )
        )
        model.add_result(
            ResultField(
                name='von_mises',
                association='cell',
                values=increment_result.cell_vm_full.copy(),
                stage=stage_name,
            )
        )
        return {
            'status': increment_result.status,
            'field_names': (
                'U',
                'U_mag',
                'dU',
                'dU_mag',
                'residual',
                'residual_mag',
                'reaction',
                'reaction_mag',
                'stress',
                'von_mises',
            ),
            'assembly_info': dict(increment_result.assembly_info),
        }

    def capture_runtime_arrays(self, runtime_state: _ReferenceRuntimeState) -> dict[str, np.ndarray]:
        return {
            'total_u': np.asarray(runtime_state.total_u, dtype=float).copy(),
            'stage_start_total_u': np.asarray(runtime_state.stage_start_total_u, dtype=float).copy(),
            'stage_current_u': np.asarray(runtime_state.stage_current_u, dtype=float).copy(),
            'residual': np.asarray(runtime_state.residual_full, dtype=float).copy(),
            'reaction': np.asarray(runtime_state.reaction_full, dtype=float).copy(),
            'cell_stress': np.asarray(runtime_state.cell_stress_full, dtype=float).copy(),
            'cell_vm': np.asarray(runtime_state.cell_vm_full, dtype=float).copy(),
        }

    def capture_runtime_resume_payload(
        self,
        runtime_state: _ReferenceRuntimeState,
    ) -> dict[str, object]:
        return {
            'stage_names': list(runtime_state.stage_names),
            'stage_modes': dict(runtime_state.stage_modes),
            'linear_assembly_meta': {
                name: dict(meta)
                for name, meta in runtime_state.linear_assembly_meta.items()
            },
            'notes': list(runtime_state.notes),
            'solver_history': {
                name: [dict(row) for row in rows]
                for name, rows in runtime_state.solver_history.items()
            },
            'step_control_trace': {
                name: [dict(row) for row in rows]
                for name, rows in runtime_state.step_control_trace.items()
            },
            'active_stage_name': runtime_state.active_stage_name,
        }

    def restore_runtime_state(
        self,
        runtime_state: _ReferenceRuntimeState,
        *,
        arrays: dict[str, np.ndarray] | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        arrays = dict(arrays or {})
        payload = dict(payload or {})
        resume_mode = str(payload.get('resume_mode') or 'restore-checkpoint')
        if 'total_u' in arrays:
            runtime_state.total_u = np.asarray(arrays['total_u'], dtype=float).copy()
        if 'stage_start_total_u' in arrays:
            runtime_state.stage_start_total_u = np.asarray(
                arrays['stage_start_total_u'],
                dtype=float,
            ).copy()
        else:
            runtime_state.stage_start_total_u = runtime_state.total_u.copy()
        if 'cell_stress' in arrays:
            runtime_state.cell_stress_full = np.asarray(arrays['cell_stress'], dtype=float).copy()
        if 'cell_vm' in arrays:
            runtime_state.cell_vm_full = np.asarray(arrays['cell_vm'], dtype=float).copy()
        if 'stage_current_u' in arrays:
            runtime_state.stage_current_u = np.asarray(arrays['stage_current_u'], dtype=float).copy()
        else:
            runtime_state.stage_current_u = np.zeros_like(runtime_state.total_u)
        if 'residual' in arrays:
            runtime_state.residual_full = np.asarray(arrays['residual'], dtype=float).copy()
        else:
            runtime_state.residual_full = np.zeros_like(runtime_state.total_u)
        if 'reaction' in arrays:
            runtime_state.reaction_full = np.asarray(arrays['reaction'], dtype=float).copy()
        else:
            runtime_state.reaction_full = np.zeros_like(runtime_state.total_u)
        if resume_mode == 'rollback-stage-start':
            runtime_state.total_u = runtime_state.stage_start_total_u.copy()
            runtime_state.stage_current_u = np.zeros_like(runtime_state.total_u)
            runtime_state.residual_full = np.zeros_like(runtime_state.total_u)
            runtime_state.reaction_full = np.zeros_like(runtime_state.total_u)
        runtime_state.stage_names = [str(item) for item in payload.get('stage_names', []) or []]
        runtime_state.stage_modes = {
            str(name): str(mode)
            for name, mode in dict(payload.get('stage_modes', {}) or {}).items()
        }
        runtime_state.linear_assembly_meta = {
            str(name): dict(meta)
            for name, meta in dict(payload.get('linear_assembly_meta', {}) or {}).items()
        }
        runtime_state.notes = [str(item) for item in payload.get('notes', []) or []]
        runtime_state.solver_history = {
            str(name): [dict(row) for row in rows]
            for name, rows in dict(payload.get('solver_history', {}) or {}).items()
        }
        runtime_state.step_control_trace = {
            str(name): [dict(row) for row in rows]
            for name, rows in dict(payload.get('step_control_trace', {}) or {}).items()
        }
        active_stage_name = payload.get('active_stage_name')
        runtime_state.active_stage_name = None if active_stage_name in {None, ''} else str(active_stage_name)

    def finalize_runtime_state(
        self,
        model: SimulationModel,
        settings: SolverSettings,
        runtime_state: _ReferenceRuntimeState,
    ) -> SimulationModel:
        grid = model.to_unstructured_grid()
        grid.point_data['U'] = runtime_state.total_u
        grid.point_data['U_mag'] = np.linalg.norm(runtime_state.total_u, axis=1)
        grid.point_data['residual'] = runtime_state.residual_full
        grid.point_data['residual_mag'] = np.linalg.norm(runtime_state.residual_full, axis=1)
        grid.point_data['reaction'] = runtime_state.reaction_full
        grid.point_data['reaction_mag'] = np.linalg.norm(runtime_state.reaction_full, axis=1)
        grid.cell_data['stress'] = runtime_state.cell_stress_full
        grid.cell_data['von_mises'] = runtime_state.cell_vm_full
        grid.point_data['X0'] = runtime_state.x0
        grid.point_data['Z0'] = runtime_state.x0[:, 2]
        grid.points = runtime_state.x0 + settings.displacement_scale * runtime_state.total_u
        model.mesh = grid
        model.metadata['backend'] = 'reference-linear'
        model.metadata['compute_device'] = 'cpu'
        model.metadata['thread_count'] = int(settings.thread_count)
        model.metadata['stages_run'] = list(runtime_state.stage_names)
        model.metadata['stage_solver_modes'] = dict(runtime_state.stage_modes)
        model.metadata['linear_element_assembly'] = dict(runtime_state.linear_assembly_meta)
        model.metadata['solver_history'] = {
            name: [dict(row) for row in rows]
            for name, rows in runtime_state.solver_history.items()
        }
        model.metadata['step_control_trace'] = {
            name: [dict(row) for row in rows]
            for name, rows in runtime_state.step_control_trace.items()
        }
        model.metadata['solver_backend'] = 'reference'
        model.metadata['solver_backend_chain'] = ['reference']
        model.metadata['stage_execution_diagnostics'] = self.stage_execution_diagnostics(model, settings)
        model.metadata['solver_mode'] = (
            'linear-hex8'
            if runtime_state.family == 'hex8'
            else 'linear-tet4'
        )
        model.metadata['solver_execution_mode'] = 'stage-runtime'
        model.metadata['solver_note'] = (
            'Executed the rebuilt reference staged runtime backend.'
            if runtime_state.stage_names
            else 'Executed the rebuilt reference runtime backend.'
        )
        if runtime_state.notes:
            model.metadata['solver_warnings'] = list(runtime_state.notes)
        return model

    def solve(self, model: SimulationModel, settings: SolverSettings) -> SimulationModel:
        model.ensure_regions()
        supported, reason = self._supported_linear_continuum(model)
        if str(settings.metadata.get('solver_backend') or '').strip().lower() == 'legacy-warp':
            return self._fallback(model, settings, 'settings requested the legacy warp backend')
        if not supported:
            return self._fallback(model, settings, reason)

        family = self._mesh_family(model)
        if family == 'mixed':
            return self._fallback(model, settings, 'mixed or unsupported cell families are not on the reference path')

        try:
            runtime_state = self.initialize_runtime_state(model, settings)
        except Exception as exc:
            return self._fallback(model, settings, str(exc))

        for stage_ctx in StageManager(model).iter_stages():
            stage = stage_ctx.stage
            self.begin_stage(runtime_state, stage_name=stage.name)
            target_steps = max(1, int(stage.steps or 1))
            history_rows: list[dict[str, Any]] = []
            step_trace_rows: list[dict[str, Any]] = []
            increment_result: _StageIncrementResult | None = None
            for increment_index in range(1, target_steps + 1):
                factor = float(increment_index) / float(target_steps)
                increment_result = self.advance_stage_increment(
                    model,
                    settings,
                    runtime_state,
                    stage_name=stage.name,
                    active_regions=stage_ctx.active_regions,
                    bcs=tuple(model.boundary_conditions) + tuple(stage.boundary_conditions),
                    loads=tuple(stage.loads),
                    load_factor=factor,
                    increment_index=increment_index,
                    increment_count=target_steps,
                    stage_metadata=dict(stage.metadata or {}),
                )
                history_rows.append(
                    {
                        'iteration': int(increment_index),
                        'linear_backend': 'reference',
                        'load_factor': float(factor),
                        'status': increment_result.status,
                        'active_cell_count': int(increment_result.active_cell_count),
                    }
                )
                step_trace_rows.append(
                    {
                        'step': int(increment_index),
                        'factor': float(factor),
                        'status': increment_result.status,
                    }
                )

            if increment_result is None:
                continue
            self.commit_stage(
                model,
                runtime_state,
                stage_name=stage.name,
                increment_result=increment_result,
                history_rows=history_rows,
                step_trace_rows=step_trace_rows,
            )

        return self.finalize_runtime_state(model, settings, runtime_state)
