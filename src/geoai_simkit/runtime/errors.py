from __future__ import annotations


class RecoverableIncrementError(RuntimeError):
    """A stage increment failure that may be retried via cutback/rollback."""

