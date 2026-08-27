"""Pipeline run metadata helpers (DynamoDB wiring lands in a later feat)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lakehouse.models import PipelineRun, PipelineStatus, Zone


def new_run(*, zone: Zone | None = None, status: PipelineStatus = "pending") -> PipelineRun:
    return PipelineRun(
        run_id=str(uuid4()),
        started_at=datetime.now(tz=UTC),
        status=status,
        zone=zone,
    )
