from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from lakehouse.storage import keys_from_event, list_keys, load_json, load_pairs, put_json


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        body = kwargs["Body"]
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = body
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        key = (kwargs["Bucket"], kwargs["Key"])
        if key not in self.objects:
            raise KeyError(key)
        return {"Body": BytesIO(self.objects[key])}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = kwargs.get("Prefix", "")
        bucket = kwargs["Bucket"]
        contents = [
            {"Key": key} for (b, key) in self.objects if b == bucket and key.startswith(prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


def test_put_load_and_list_roundtrip() -> None:
    s3 = FakeS3()
    put_json(s3, "b", "events/dt=2026-01-02/a.json", {"event_id": "a"})
    put_json(s3, "b", "events/", b"")
    assert load_json(s3, "b", "events/dt=2026-01-02/a.json") == {"event_id": "a"}
    assert load_json(s3, "b", "missing") is None
    keys = list_keys(s3, "b", "events/")
    assert "events/dt=2026-01-02/a.json" in keys


def test_keys_from_event_skips_other_prefixes() -> None:
    s3 = FakeS3()
    put_json(s3, "b", "events/one.json", {"ok": True})
    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {"bucket": {"name": "b"}, "object": {"key": "events/one.json"}},
            },
            {
                "eventSource": "aws:s3",
                "s3": {"bucket": {"name": "b"}, "object": {"key": "tmp/ignore.json"}},
            },
        ]
    }
    accepted, skipped = keys_from_event(event, default_bucket="b", s3=s3)
    assert accepted == [("b", "events/one.json")]
    assert skipped == ["tmp/ignore.json"]
    records, keys, missing = load_pairs(s3, accepted)
    assert records == [{"ok": True}]
    assert keys == ["events/one.json"]
    assert missing == []


def test_empty_event_lists_prefix() -> None:
    s3 = FakeS3()
    put_json(s3, "b", "events/one.json", {"ok": 1})
    accepted, skipped = keys_from_event(None, default_bucket="b", s3=s3)
    assert accepted == [("b", "events/one.json")]
    assert skipped == []


def test_load_json_handles_invalid_payload() -> None:
    s3 = FakeS3()
    s3.put_object(Bucket="b", Key="events/raw.json", Body=b"not-json")
    payload = load_json(s3, "b", "events/raw.json")
    assert payload == {"_raw": "not-json", "event_id": ""}
    s3.put_object(Bucket="b", Key="events/list.json", Body=json.dumps([1, 2]).encode())
    payload = load_json(s3, "b", "events/list.json")
    assert payload == {"_raw": [1, 2], "event_id": ""}
