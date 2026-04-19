from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class SparseBlockMatrix:
    pattern: Any | None = None
    values: Any | None = None
    block_size: int = 1
    shape: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_matrix(
        cls,
        matrix: Any,
        *,
        block_size: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> 'SparseBlockMatrix':
        meta = dict(metadata or {})
        resolved_block_size = max(1, int(getattr(matrix, 'block_size', block_size) or block_size or 1))

        if hasattr(matrix, 'to_csr') or hasattr(matrix, 'tocsr'):
            csr = matrix.to_csr() if hasattr(matrix, 'to_csr') else matrix.tocsr()
            shape = tuple(int(item) for item in getattr(csr, 'shape', (0, 0)))
            storage_bytes = int(
                np.asarray(getattr(csr, 'data', np.empty((0,), dtype=float))).nbytes
                + np.asarray(getattr(csr, 'indices', np.empty((0,), dtype=np.int64))).nbytes
                + np.asarray(getattr(csr, 'indptr', np.empty((0,), dtype=np.int64))).nbytes
            )
            meta.setdefault('storage', 'csr')
            meta.setdefault('nnz_entries', int(getattr(csr, 'nnz', 0) or 0))
            meta.setdefault(
                'nnz_blocks',
                int(np.ceil(float(meta['nnz_entries']) / float(resolved_block_size * resolved_block_size)))
                if int(meta['nnz_entries']) > 0
                else 0,
            )
            meta.setdefault('storage_bytes', storage_bytes)
            return cls(
                pattern=csr,
                values=np.asarray(getattr(csr, 'data', np.empty((0,), dtype=float))).copy(),
                block_size=resolved_block_size,
                shape=shape,
                metadata=meta,
            )

        array = np.asarray(matrix, dtype=float)
        shape = tuple(int(item) for item in array.shape[:2]) if array.ndim >= 2 else (int(array.size), int(array.size))
        nnz_entries = int(np.count_nonzero(array))
        meta.setdefault('storage', 'dense')
        meta.setdefault('nnz_entries', nnz_entries)
        meta.setdefault(
            'nnz_blocks',
            int(np.ceil(float(nnz_entries) / float(resolved_block_size * resolved_block_size)))
            if nnz_entries > 0
            else 0,
        )
        meta.setdefault('storage_bytes', int(array.nbytes))
        return cls(
            pattern=array.copy(),
            values=array.copy(),
            block_size=resolved_block_size,
            shape=shape,
            metadata=meta,
        )

    @classmethod
    def from_summary(
        cls,
        summary: dict[str, Any] | None,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> 'SparseBlockMatrix':
        meta = dict(summary or {})
        meta.update(dict(metadata or {}))
        shape_obj = meta.get('shape', meta.get('matrix_shape'))
        shape = None
        if isinstance(shape_obj, (list, tuple)) and len(shape_obj) >= 2:
            shape = (int(shape_obj[0]), int(shape_obj[1]))
        return cls(
            pattern=None,
            values=None,
            block_size=max(1, int(meta.get('block_size', 1) or 1)),
            shape=shape,
            metadata=meta,
        )

    def to_csr(self) -> Any:
        if self.pattern is not None and (hasattr(self.pattern, 'to_csr') or hasattr(self.pattern, 'tocsr')):
            return self.pattern.to_csr() if hasattr(self.pattern, 'to_csr') else self.pattern.tocsr()
        if self.pattern is not None:
            array = np.asarray(self.pattern, dtype=float)
            try:
                from scipy import sparse as sp  # type: ignore
            except Exception:  # pragma: no cover - optional dependency
                return array
            return sp.csr_matrix(array)
        rows = 0 if self.shape is None else int(self.shape[0])
        cols = 0 if self.shape is None else int(self.shape[1])
        try:
            from scipy import sparse as sp  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            return np.zeros((rows, cols), dtype=float)
        return sp.csr_matrix((rows, cols), dtype=float)

    def resolved_shape(self) -> tuple[int, int]:
        if self.shape is not None:
            return (int(self.shape[0]), int(self.shape[1]))
        if self.pattern is not None and hasattr(self.pattern, 'shape'):
            shape = getattr(self.pattern, 'shape', (0, 0))
            return (int(shape[0]), int(shape[1]))
        return (0, 0)

    def nnz_entries(self) -> int:
        if self.pattern is not None and hasattr(self.pattern, 'nnz'):
            return int(getattr(self.pattern, 'nnz', 0) or 0)
        if self.pattern is not None:
            return int(np.count_nonzero(np.asarray(self.pattern, dtype=float)))
        return int(self.metadata.get('nnz_entries', 0) or 0)

    def nnz_blocks(self) -> int:
        if self.metadata.get('nnz_blocks') is not None:
            return int(self.metadata.get('nnz_blocks', 0) or 0)
        entries = self.nnz_entries()
        if entries <= 0:
            return 0
        return int(np.ceil(float(entries) / float(max(1, self.block_size * self.block_size))))

    def density(self) -> float:
        rows, cols = self.resolved_shape()
        if rows <= 0 or cols <= 0:
            return 0.0
        return float(self.nnz_entries() / float(rows * cols))

    def storage_bytes(self) -> int:
        if self.metadata.get('storage_bytes') is not None:
            return int(self.metadata.get('storage_bytes', 0) or 0)
        if self.pattern is not None and hasattr(self.pattern, 'nnz'):
            csr = self.to_csr()
            return int(
                np.asarray(getattr(csr, 'data', np.empty((0,), dtype=float))).nbytes
                + np.asarray(getattr(csr, 'indices', np.empty((0,), dtype=np.int64))).nbytes
                + np.asarray(getattr(csr, 'indptr', np.empty((0,), dtype=np.int64))).nbytes
            )
        if self.pattern is not None:
            return int(np.asarray(self.pattern, dtype=float).nbytes)
        return 0

    def summary(self) -> dict[str, Any]:
        rows, cols = self.resolved_shape()
        payload = {
            'shape': [int(rows), int(cols)],
            'block_size': int(self.block_size),
            'storage': str(self.metadata.get('storage', 'summary-only')),
            'nnz_entries': int(self.nnz_entries()),
            'nnz_blocks': int(self.nnz_blocks()),
            'density': float(self.density()),
            'storage_bytes': int(self.storage_bytes()),
        }
        for key, value in self.metadata.items():
            if key in payload:
                continue
            payload[key] = value
        return payload
