from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MohrCoulombDescriptor:
    name: str = 'mohr_coulomb'
    parameters: dict[str, Any] = field(default_factory=dict)
