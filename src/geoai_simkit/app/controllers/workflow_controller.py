from __future__ import annotations

"""Thin GUI-facing controller for the canonical headless workflow service."""

from typing import Any

from geoai_simkit.contracts import ProjectWorkflowReport
from geoai_simkit.services import run_project_workflow


def run_headless_project_workflow(project: Any, **kwargs: Any) -> ProjectWorkflowReport:
    """Run the modular workflow without importing solver/mesh internals here."""

    return run_project_workflow(project, **kwargs)


__all__ = ["run_headless_project_workflow"]
