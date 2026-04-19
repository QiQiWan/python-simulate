from __future__ import annotations

from typing import Any

import numpy as np

from .schemas import HaloExchangePlan


class Communicator:
    def barrier(self) -> None:
        return None

    def allreduce_sum(self, value: Any):
        return value

    def allreduce_max(self, value: Any):
        return value

    def exchange(
        self,
        plan: HaloExchangePlan,
        send_buffers: dict[str, object],
    ) -> dict[str, object]:
        return dict(send_buffers)


class LocalCommunicator(Communicator):
    pass


class ThreadCommunicator(Communicator):
    pass


class MpiCommunicator(Communicator):
    def exchange(
        self,
        plan: HaloExchangePlan,
        send_buffers: dict[str, object],
    ) -> dict[str, object]:
        mirrored: dict[str, object] = {}
        for key, value in send_buffers.items():
            if isinstance(value, np.ndarray):
                mirrored[key] = value.copy()
            else:
                mirrored[key] = value
        return mirrored


def make_communicator(name: str | None) -> Communicator:
    token = str(name or 'local').strip().lower()
    if token == 'thread':
        return ThreadCommunicator()
    if token == 'mpi':
        return MpiCommunicator()
    return LocalCommunicator()
