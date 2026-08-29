from __future__ import annotations

from typing import Any

from lakehouse.pipeline.idempotency import (
    content_hash,
    deterministic_run_id,
    idempotency_key,
    lookup_succeeded,
    replay_result,
)
from lakehouse.pipeline.runs import complete_run, new_run, persist_run


class FakeDDB:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        item = kwargs["Item"]
        self.store[item["run_id"]["S"]] = item
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        run_id = kwargs["Key"]["run_id"]["S"]
        item = self.store.get(run_id)
        return {"Item": item} if item else {}


def test_content_hash_is_stable_and_order_sensitive() -> None:
    assert content_hash(["a", "b"]) == content_hash(["a", "b"])
    assert content_hash(["a", "b"]) != content_hash(["b", "a"])
    assert len(content_hash(["x"])) == 64


def test_idempotency_key_sorts_parts_and_scopes() -> None:
    left = idempotency_key("bronze", "events/b.json", "events/a.json")
    right = idempotency_key("bronze", "events/a.json", "events/b.json")
    assert left == right
    assert left.startswith("bronze#")
    assert idempotency_key("silver", "events/a.json") != left


def test_deterministic_run_id_is_short_and_stable() -> None:
    first = deterministic_run_id("gold", "events/a.json")
    second = deterministic_run_id("gold", "events/a.json")
    assert first == second
    assert first.startswith("gold-")
    assert len(first) == len("gold-") + 16


def test_lookup_succeeded_ignores_failed_and_replays_success() -> None:
    ddb = FakeDDB()
    run_id = deterministic_run_id("bronze", "events/a.json")
    failed = complete_run(
        new_run(zone="bronze", status="running", run_id=run_id),
        status="failed",
        error="boom",
        objects=["events/a.json"],
    )
    persist_run(ddb, "runs", failed)
    assert lookup_succeeded(ddb, "runs", run_id) is None

    ok = complete_run(
        new_run(zone="bronze", status="running", run_id=run_id),
        status="succeeded",
        objects=["events/a.json"],
        metrics={"object_count": 1},
    )
    persist_run(ddb, "runs", ok)
    loaded = lookup_succeeded(ddb, "runs", run_id)
    assert loaded is not None
    replay = replay_result(loaded, skipped=[])
    assert replay["idempotent_replay"] is True
    assert replay["run_id"] == run_id
    assert replay["accepted"] == ["events/a.json"]
