from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .iterative import solve_iterative
from .sparse_block import SparseBlockMatrix


@dataclass(slots=True)
class LinearSystemOperator:
    matrix: Any | None = None
    rhs: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_matrix(
        cls,
        matrix: Any,
        rhs: Any | None = None,
        *,
        block_size: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> 'LinearSystemOperator':
        matrix_obj = matrix if isinstance(matrix, SparseBlockMatrix) else SparseBlockMatrix.from_matrix(
            matrix,
            block_size=block_size,
            metadata=dict(metadata or {}),
        )
        return cls(matrix=matrix_obj, rhs=rhs, metadata=dict(metadata or {}))

    @classmethod
    def from_summary(
        cls,
        summary: dict[str, Any] | None,
        *,
        rhs: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> 'LinearSystemOperator':
        matrix_summary = SparseBlockMatrix.from_summary(summary, metadata=metadata)
        return cls(matrix=matrix_summary, rhs=rhs, metadata=dict(metadata or {}))

    def matrix_summary(self) -> dict[str, Any]:
        if self.matrix is None:
            return {}
        if isinstance(self.matrix, SparseBlockMatrix):
            return self.matrix.summary()
        return SparseBlockMatrix.from_matrix(self.matrix).summary()

    def rhs_size(self) -> int:
        if self.rhs is None:
            return int(self.metadata.get('rhs_size', 0) or 0)
        return int(np.asarray(self.rhs, dtype=float).size)

    def rhs_norm(self) -> float:
        if self.rhs is None:
            return float(self.metadata.get('rhs_norm', 0.0) or 0.0)
        return float(np.linalg.norm(np.asarray(self.rhs, dtype=float).reshape(-1)))

    def summary(self) -> dict[str, Any]:
        matrix_summary = self.matrix_summary()
        shape = matrix_summary.get('shape', [0, 0])
        payload = {
            'ndof': int(shape[0]) if isinstance(shape, list) and shape else 0,
            'rhs_size': int(self.rhs_size()),
            'rhs_norm': float(self.rhs_norm()),
            'matrix': matrix_summary,
        }
        for key, value in self.metadata.items():
            if key in payload:
                continue
            payload[key] = value
        return payload

    def solve(self, *, context=None, **kwargs):
        if self.matrix is None or self.rhs is None:
            raise ValueError('LinearSystemOperator.solve() requires both matrix and rhs.')
        matrix = self.matrix.to_csr() if isinstance(self.matrix, SparseBlockMatrix) else self.matrix
        return solve_iterative(matrix, self.rhs, context=context, **kwargs)
