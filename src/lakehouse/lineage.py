"""Dataset lineage for one medallion run.

MiniStack CI is hermetic, so this module always builds a spec graph
(Bronze raw → Silver cleansed → quality report → Gold metrics **or**
Gold quarantine rejected-metrics + run row) and optionally folds in
live DynamoDB runs and S3 object counts.

``python -m lakehouse lineage`` prints JSON. ``--out`` writes Mermaid.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings


def _endpoint_reachable(url: str | None, timeout: float = 0.4) -> bool:
    """Cheap TCP probe so unit tests do not block on a down MiniStack."""

    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


ZONES = ("bronze", "silver", "quality", "gold", "gold_quarantine", "runs")

SPEC_EDGES: tuple[tuple[str, str, str], ...] = (
    ("bronze", "silver", "cleanse"),
    ("silver", "quality", "gate"),
    ("quality", "gold", "aggregate"),
    ("quality", "gold_quarantine", "reject"),
    ("silver", "gold_quarantine", "unreadable"),
    ("bronze", "runs", "run_metadata"),
    ("silver", "runs", "run_metadata"),
    ("quality", "runs", "run_metadata"),
    ("gold", "runs", "run_metadata"),
    ("gold_quarantine", "runs", "run_metadata"),
)
