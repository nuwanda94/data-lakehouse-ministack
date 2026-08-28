"""Typed records that move between bronze, silver, and gold zones."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Zone = Literal["bronze", "silver", "gold"]
PipelineStatus = Literal["pending", "running", "succeeded", "failed", "quality_failed"]
PipelineStep = Literal["ingest", "silver", "quality", "gold", "pipeline"]


class CommerceEvent(BaseModel):
    """Canonical synthetic commerce event landed in bronze as JSON."""

    event_id: str
    event_ts: datetime
    event_type: str
    user_id: str
    sku: str
    quantity: int = Field(ge=0)
    amount_usd: float = Field(ge=0)
    country: str = "US"


class QualityResult(BaseModel):
    check_name: str
    passed: bool
    rows_scanned: int = 0
    rows_failed: int = 0
    detail: str = ""


class PipelineRun(BaseModel):
    """One pipeline (or zone-step) execution recorded in DynamoDB."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: PipelineStatus = "pending"
    zone: Zone | None = None
    step: PipelineStep | None = None
    parent_run_id: str | None = None
    quality: list[QualityResult] = Field(default_factory=list)
    error: str | None = None
    objects: list[str] = Field(default_factory=list)
    metrics: dict[str, int | float | str] = Field(default_factory=dict)
