from __future__ import annotations

"""Backward-compatible import path for the headless job service."""

from geoai_simkit.services.job_service import JobPlanSummary, JobRunSummary, JobService

__all__ = ["JobPlanSummary", "JobRunSummary", "JobService"]
