from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

ArrayF = np.ndarray
Association = Literal["point", "cell"]


@dataclass(slots=True)
class RegionTag:
    name: str
    cell_ids: ArrayF
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResultField:
    name: str
    association: Association
    values: ArrayF
    components: int = 1
    stage: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
