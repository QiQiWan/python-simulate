from __future__ import annotations

from .base import Operator, OperatorContribution


class ContactOperator(Operator):
    name = 'contact'

    def evaluate(self, state, context):
        return OperatorContribution(
            diagnostics={
                'operator': self.name,
                'stage': context.stage_name,
                'partition_id': context.partition_id,
                'load_factor': float(context.load_factor),
                'implemented_via_interface_operator': bool(
                    state.get('implemented_via_interface_operator', True)
                ),
                'active_contact_pair_count': int(state.get('count', 0) or 0),
                'closed_pair_count': int(state.get('closed_pair_count', 0) or 0),
                'open_pair_count': int(state.get('open_pair_count', 0) or 0),
                'coupling_model': str(
                    state.get('coupling_model', 'node-pair-penalty-contact')
                ),
                'friction_model': str(
                    state.get('friction_model', 'coulomb-penalty')
                ),
                'warning_count': int(len(state.get('warnings', []) or [])),
                'warnings': [str(item) for item in state.get('warnings', []) or []],
            }
        )
