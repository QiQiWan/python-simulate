from __future__ import annotations

from .base import Operator, OperatorContribution


class BoundaryOperator(Operator):
    name = 'boundary'

    def evaluate(self, state, context):
        boundary_condition_kinds = [
            str(item)
            for item in state.get('boundary_condition_kinds', []) or []
        ]
        load_kinds = [
            str(item)
            for item in state.get('load_kinds', []) or []
        ]
        return OperatorContribution(
            diagnostics={
                'operator': self.name,
                'stage': context.stage_name,
                'partition_id': context.partition_id,
                'load_factor': float(context.load_factor),
                'boundary_condition_count': int(
                    state.get('boundary_condition_count', 0) or 0
                ),
                'load_count': int(state.get('load_count', 0) or 0),
                'boundary_condition_kinds': boundary_condition_kinds,
                'load_kinds': load_kinds,
                'active_support_groups': [
                    str(item)
                    for item in state.get('active_support_groups', []) or []
                ],
                'active_interface_groups': [
                    str(item)
                    for item in state.get('active_interface_groups', []) or []
                ],
            }
        )
