"""Typed records that move between bronze, silver, and gold zones."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Zone = Literal["bronze", "silver", "gold"]
PipelineStatus = Literal["pending", "running", "succeeded", "failed", "quality_failed"]


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
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: PipelineStatus = "pending"
    zone: Zone | None = None
    quality: list[QualityResult] = Field(default_factory=list)
    error: str | None = None
