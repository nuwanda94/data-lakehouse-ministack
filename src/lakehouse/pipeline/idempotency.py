"""Content-hash idempotency keys and deterministic run IDs.

Retries of the same Bronze / Silver / Gold payload reuse one run_id so
SQS redrives and Step Functions retries do not mint a new identity.
A run that already succeeded is replayed instead of being written twice
(exactly-once *effect* on top of at-least-once delivery).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from lakehouse.models import PipelineRun
from lakehouse.pipeline.runs import get_run

TERMINAL_SUCCESS = frozenset({"succeeded"})


def content_hash(parts: Iterable[str | bytes]) -> str:
    """Stable SHA-256 over length-prefixed parts (order-preserving)."""

    digest = hashlib.sha256()
    for part in parts:
        raw = part.encode("utf-8") if isinstance(part, str) else part
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
    return digest.hexdigest()


def idempotency_key(scope: str, *parts: str) -> str:
    """``scope#sha256`` over the scope plus sorted non-empty parts."""

    material = [scope, *sorted(p for p in parts if p)]
    return f"{scope}#{content_hash(material)}"


def deterministic_run_id(scope: str, *parts: str) -> str:
    """Short, collision-resistant run_id derived from the idempotency key."""

    key = idempotency_key(scope, *parts)
    digest = key.split("#", 1)[1][:16]
    return f"{scope}-{digest}"


def lookup_succeeded(ddb: Any, table: str, run_id: str) -> PipelineRun | None:
    """Return the existing run when it already completed successfully."""

    existing = get_run(ddb, table, run_id)
    if existing is None:
        return None
    if existing.status in TERMINAL_SUCCESS:
        return existing
    return None


def replay_result(run: PipelineRun, **extra: Any) -> dict[str, Any]:
    """Handler response for a short-circuited retry of a succeeded run."""

    payload: dict[str, Any] = {
        "run_id": run.run_id,
        "status": run.status,
        "idempotent_replay": True,
        "accepted": list(run.objects),
        "metrics": dict(run.metrics),
    }
    payload.update(extra)
    return payload
