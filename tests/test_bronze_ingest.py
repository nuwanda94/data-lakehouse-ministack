from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from lakehouse.config import Settings
from lakehouse.ingest.bronze_handler import ingest_bronze_event
from lakehouse.ingest.s3_events import extract_object_refs
from lakehouse.pipeline.idempotency import deterministic_run_id


def _settings() -> Settings:
    return Settings(
        aws_endpoint_url="http://localhost:4566",
        aws_region="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        bronze_bucket="b",
        silver_bucket="s",
        gold_bucket="g",
        pipeline_runs_table="runs",
        gold_metrics_table="metrics",
        bronze_events_queue="lakehouse-local-bronze-events",
        bronze_events_queue_url="",
    )


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        body = kwargs["Body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = body
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = (kwargs["Bucket"], kwargs["Key"])
        if key not in self.objects:
            raise KeyError(key)
        return {"ContentLength": len(self.objects[key])}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        data = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        return {"Body": BytesIO(data)}


class FakeDDB:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        item = kwargs["Item"]
        run_id = item.get("run_id", {}).get("S")
        self.items = [i for i in self.items if i.get("run_id", {}).get("S") != run_id]
        self.items.append(item)
        return {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        run_id = kwargs["Key"]["run_id"]["S"]
        for item in self.items:
            if item.get("run_id", {}).get("S") == run_id:
                return {"Item": item}
        return {}


def test_extract_native_s3_event() -> None:
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": "lakehouse-local-bronze"},
                    "object": {"key": "events/dt=2026-01-02/evt-1.json"},
                },
            }
        ]
    }
    refs = extract_object_refs(event)
    assert len(refs) == 1
    assert refs[0].bucket == "lakehouse-local-bronze"
    assert refs[0].key == "events/dt=2026-01-02/evt-1.json"
    assert refs[0].source == "s3"


def test_extract_sqs_wrapped_s3_event_url_decodes_key() -> None:
    inner = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt%3D2026-01-02/evt+1.json"},
                },
            }
        ]
    }
    event = {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "body": json.dumps(inner),
            }
        ]
    }
    refs = extract_object_refs(event)
    assert refs[0].key == "events/dt=2026-01-02/evt 1.json"
    assert refs[0].source == "sqs"


def test_extract_eventbridge_detail() -> None:
    event = {
        "detail-type": "Object Created",
        "detail": {
            "bucket": {"name": "b"},
            "object": {"key": "events/dt=2026-01-02/evt-9.json"},
        },
    }
    refs = extract_object_refs(event)
    assert refs[0].key.endswith("evt-9.json")
    assert refs[0].source == "eventbridge"


def test_handler_writes_run_metadata_for_existing_object() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(Bucket="b", Key="events/dt=2026-01-02/evt-1.json", Body=b"{}")
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt=2026-01-02/evt-1.json"},
                },
            },
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "tmp/ignore.json"},
                },
            },
        ]
    }
    result = ingest_bronze_event(event, settings=_settings(), s3=s3, ddb=ddb)
    assert result["status"] == "succeeded"
    assert result["accepted"] == ["events/dt=2026-01-02/evt-1.json"]
    assert result["skipped"] == ["tmp/ignore.json"]
    assert result["idempotent_replay"] is False
    expected_id = deterministic_run_id("bronze", "events/dt=2026-01-02/evt-1.json")
    assert result["run_id"] == expected_id
    assert ddb.items[0]["zone"]["S"] == "bronze"
    assert ddb.items[0]["object_count"]["N"] == "1"


def test_handler_replays_succeeded_run_on_retry() -> None:
    s3 = FakeS3()
    ddb = FakeDDB()
    s3.put_object(Bucket="b", Key="events/dt=2026-01-02/evt-1.json", Body=b"{}")
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "events/dt=2026-01-02/evt-1.json"},
                },
            }
        ]
    }
    first = ingest_bronze_event(event, settings=_settings(), s3=s3, ddb=ddb)
    second = ingest_bronze_event(event, settings=_settings(), s3=s3, ddb=ddb)
    assert first["run_id"] == second["run_id"]
    assert second["idempotent_replay"] is True
    assert len(ddb.items) == 1


def test_handler_fails_when_all_objects_missing() -> None:
    result = ingest_bronze_event(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "events/dt=2026-01-02/gone.json"},
                    },
                }
            ]
        },
        settings=_settings(),
        s3=FakeS3(),
        ddb=FakeDDB(),
    )
    assert result["status"] == "failed"
    assert result["missing"]
