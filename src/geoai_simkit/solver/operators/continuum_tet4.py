from __future__ import annotations

from geoai_simkit.solver.linsys import LinearSystemOperator

from .base import Operator, OperatorContribution


class ContinuumTet4Operator(Operator):
    name = 'continuum_tet4'
    element_family = 'tet4'

    def evaluate(self, state, context):
        assembly_info = dict(state.get('assembly_info', {}) or {})
        linear_system_summary = dict(state.get('linear_system_summary', {}) or {})
        partition_local_systems = [
            dict(item)
            for item in state.get('partition_linear_systems', []) or []
        ]
        active_cell_count = int(
            state.get(
                'active_cell_count',
                assembly_info.get('element_count', 0),
            )
            or 0
        )
        active_node_count = int(state.get('active_node_count', 0) or 0)
        gp_per_cell = int(state.get('gauss_points_per_cell', 1) or 1)
        linear_system = LinearSystemOperator.from_summary(
            linear_system_summary,
            metadata={
                'operator': self.name,
                'stage_name': context.stage_name,
                'partition_id': context.partition_id,
                'rhs_size': int(linear_system_summary.get('rhs_size', 0) or 0),
                'rhs_norm': float(linear_system_summary.get('rhs_norm', 0.0) or 0.0),
                'rhs_max_abs': float(linear_system_summary.get('rhs_max_abs', 0.0) or 0.0),
                'residual_size': int(linear_system_summary.get('residual_size', 0) or 0),
                'residual_norm': float(linear_system_summary.get('residual_norm', 0.0) or 0.0),
                'residual_max_abs': float(linear_system_summary.get('residual_max_abs', 0.0) or 0.0),
                'reaction_size': int(linear_system_summary.get('reaction_size', 0) or 0),
                'reaction_dof_count': int(linear_system_summary.get('reaction_dof_count', 0) or 0),
                'reaction_norm': float(linear_system_summary.get('reaction_norm', 0.0) or 0.0),
                'reaction_max_abs': float(linear_system_summary.get('reaction_max_abs', 0.0) or 0.0),
                'fixed_dof_count': int(linear_system_summary.get('fixed_dof_count', 0) or 0),
                'free_dof_count': int(linear_system_summary.get('free_dof_count', 0) or 0),
                'solution_size': int(linear_system_summary.get('solution_size', 0) or 0),
                'solution_norm': float(linear_system_summary.get('solution_norm', 0.0) or 0.0),
                'solution_max_abs': float(linear_system_summary.get('solution_max_abs', 0.0) or 0.0),
            },
        )
        linear_system_diagnostics = dict(linear_system.summary())
        matrix_summary = dict(linear_system_diagnostics.get('matrix', {}) or {})
        if matrix_summary:
            linear_system_diagnostics.setdefault('shape', list(matrix_summary.get('shape', []) or []))
            linear_system_diagnostics.setdefault(
                'storage_bytes',
                int(matrix_summary.get('storage_bytes', 0) or 0),
            )
            linear_system_diagnostics.setdefault(
                'density',
                float(matrix_summary.get('density', 0.0) or 0.0),
            )
            linear_system_diagnostics.setdefault(
                'block_size',
                int(matrix_summary.get('block_size', linear_system_summary.get('block_size', 1)) or 1),
            )
        return OperatorContribution(
            stiffness=linear_system,
            diagnostics={
                'operator': self.name,
                'stage': context.stage_name,
                'partition_id': context.partition_id,
                'element_family': self.element_family,
                'active_cell_count': active_cell_count,
                'active_node_count': active_node_count,
                'integration_point_count': int(active_cell_count * gp_per_cell),
                'load_factor': float(context.load_factor),
                'backend': assembly_info.get('backend'),
                'device': assembly_info.get('device'),
                'linear_system': linear_system_diagnostics,
                'partition_local_systems': partition_local_systems,
                'partition_local_system_count': int(len(partition_local_systems)),
                'partition_local_rhs_size_total': int(
                    sum(int(item.get('rhs_size', 0) or 0) for item in partition_local_systems)
                ),
                'partition_local_rhs_norm_sum': float(
                    sum(float(item.get('rhs_norm', 0.0) or 0.0) for item in partition_local_systems)
                ),
                'partition_local_solution_norm_sum': float(
                    sum(float(item.get('solution_norm', 0.0) or 0.0) for item in partition_local_systems)
                ),
                'partition_local_residual_norm_sum': float(
                    sum(float(item.get('residual_norm', 0.0) or 0.0) for item in partition_local_systems)
                ),
                'partition_local_reaction_norm_sum': float(
                    sum(float(item.get('reaction_norm', 0.0) or 0.0) for item in partition_local_systems)
                ),
                'partition_local_fixed_dof_total': int(
                    sum(int(item.get('fixed_local_dof_count', 0) or 0) for item in partition_local_systems)
                ),
                'partition_local_free_dof_total': int(
                    sum(int(item.get('free_local_dof_count', 0) or 0) for item in partition_local_systems)
                ),
            },
        )
