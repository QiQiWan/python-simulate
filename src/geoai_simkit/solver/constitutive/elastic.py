from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LinearElasticDescriptor:
    name: str = 'linear_elastic'
    parameters: dict[str, Any] = field(default_factory=dict)
