from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.core.model import AnalysisStage

from .compile_config import FailurePolicy, IncrementPlan, SolverPolicy


@dataclass(slots=True)
class NonlinearController:
    solver_policy: SolverPolicy
    failure_policy: FailurePolicy

    def increment_plan_for(self, stage: AnalysisStage) -> IncrementPlan:
        stage_meta = dict(stage.metadata or {})
        target_steps = max(1, int(stage_meta.get('target_steps', stage.steps or 1) or 1))
        base_step = 1.0 / float(target_steps)
        max_cutbacks = max(
            0,
            int(stage_meta.get('max_cutbacks', self.failure_policy.max_increment_cutbacks) or 0),
        )
        initial_step_size = float(
            stage_meta.get(
                'initial_step_size',
                stage_meta.get('initial_increment', base_step),
            )
            or base_step
        )
        min_step_size = float(
            stage_meta.get('min_step_size', max(1.0e-4, base_step * 0.125))
            or max(1.0e-4, base_step * 0.125)
        )
        max_step_size = float(
            stage_meta.get('max_step_size', max(base_step, initial_step_size))
            or max(base_step, initial_step_size)
        )
        growth_factor = float(
            stage_meta.get('growth_factor', 1.25 if self.solver_policy.line_search else 1.1)
            or (1.25 if self.solver_policy.line_search else 1.1)
        )
        shrink_factor = float(
            stage_meta.get('shrink_factor', 0.5 if max_cutbacks > 0 else 1.0)
            or (0.5 if max_cutbacks > 0 else 1.0)
        )
        return IncrementPlan(
            target_steps=target_steps,
            min_step_size=max(1.0e-8, min_step_size),
            max_step_size=max(max(1.0e-8, min_step_size), max_step_size),
            growth_factor=max(1.0, growth_factor),
            shrink_factor=min(1.0, max(1.0e-6, shrink_factor)),
            target_iteration_low=4,
            target_iteration_high=max(5, int(self.solver_policy.nonlinear_max_iterations // 2)),
            metadata={
                'max_iterations': int(self.solver_policy.nonlinear_max_iterations),
                'max_cutbacks': int(max_cutbacks),
                'tolerance': float(self.solver_policy.tolerance),
                'initial_step_size': float(
                    min(max(max(1.0e-8, min_step_size), initial_step_size), max_step_size)
                ),
            },
        )
