from __future__ import annotations

from geoai_simkit.solver.linsys import LinearSystemOperator

from .base import Operator, OperatorContribution


class InterfaceOperator(Operator):
    name = 'interface'

    def evaluate(self, state, context):
        linear_system_summary = dict(state.get('linear_system_summary', {}) or {})
        linear_system = LinearSystemOperator.from_summary(
            linear_system_summary,
            metadata={
                'operator': self.name,
                'stage_name': context.stage_name,
                'partition_id': context.partition_id,
                'rhs_size': int(linear_system_summary.get('rhs_size', 0) or 0),
                'rhs_norm': float(linear_system_summary.get('rhs_norm', 0.0) or 0.0),
                'rhs_max_abs': float(
                    linear_system_summary.get('rhs_max_abs', 0.0) or 0.0
                ),
            },
        )
        return OperatorContribution(
            stiffness=linear_system,
            diagnostics={
                'operator': self.name,
                'stage': context.stage_name,
                'partition_id': context.partition_id,
                'load_factor': float(context.load_factor),
                'active_interface_count': int(state.get('count', 0) or 0),
                'kind_counts': dict(state.get('kind_counts', {}) or {}),
                'warning_count': int(len(state.get('warnings', []) or [])),
                'warnings': [str(item) for item in state.get('warnings', []) or []],
                'supported_on_reference_path': bool(
                    state.get('supported_on_reference_path', False)
                ),
                'closed_pair_count': int(state.get('closed_pair_count', 0) or 0),
                'open_pair_count': int(state.get('open_pair_count', 0) or 0),
                'internal_force_summary': dict(
                    state.get('internal_force_summary', {}) or {}
                ),
                'traction_summary': dict(state.get('traction_summary', {}) or {}),
                'linear_system': dict(linear_system.summary()),
            },
        )
