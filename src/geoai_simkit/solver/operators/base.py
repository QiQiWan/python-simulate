from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OperatorContribution:
    stiffness: Any | None = None
    residual: Any | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OperatorContext:
    stage_name: str
    partition_id: int | None = None
    load_factor: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class Operator:
    name = 'operator'

    def prepare(self, state, context: OperatorContext) -> None:
        return None

    def evaluate(self, state, context: OperatorContext) -> OperatorContribution:
        raise NotImplementedError

    def commit(self, state, context: OperatorContext) -> None:
        return None

    def rollback(self, state, context: OperatorContext) -> None:
        return None
