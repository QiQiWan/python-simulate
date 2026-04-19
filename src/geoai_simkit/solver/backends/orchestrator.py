from __future__ import annotations

from pathlib import Path

from geoai_simkit.runtime import CheckpointManager, DistributedRuntime, RuntimeConfig, checkpoint_policy_from_runtime_config

from .local_backend import LocalBackend


def build_runtime(
    runtime_config: RuntimeConfig,
    solver_settings,
    *,
    local_backend=None,
):
    checkpoint_dir = Path(runtime_config.metadata.get('checkpoint_dir') or '.runtime_checkpoints')
    checkpoint_manager = CheckpointManager(
        checkpoint_dir,
        policy=checkpoint_policy_from_runtime_config(runtime_config),
    )
    return DistributedRuntime(
        runtime_config,
        solver_settings=solver_settings,
        local_backend=local_backend or LocalBackend(),
        checkpoint_manager=checkpoint_manager,
    )
