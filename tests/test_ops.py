from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from lakehouse.config import Settings
from lakehouse.models import CommerceEvent
from lakehouse.ops.pipeline import run_pipeline
from lakehouse.ops.seed import seed_bronze
from lakehouse.pipeline.bronze import bronze_key


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

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = kwargs.get("Prefix", "")
        bucket = kwargs["Bucket"]
        contents = [
            {"Key": key}
            for (b, key), _ in self.objects.items()
            if b == bucket and key.startswith(prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        data = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        return {"Body": BytesIO(data)}


class FakeDDB:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.items.append(kwargs["Item"])
        return {}

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        return {"Items": self.items}

    def list_tables(self) -> dict[str, Any]:
        return {"TableNames": ["runs", "metrics"]}


def test_seed_bronze_writes_expected_count(monkeypatch: Any) -> None:
    fake_s3 = FakeS3()
    fake_ddb = FakeDDB()

    def _client(service: str, settings: Settings | None = None) -> Any:
        return fake_s3 if service == "s3" else fake_ddb

    monkeypatch.setattr("lakehouse.ops.seed.client", _client)
    result = seed_bronze(3, settings=_settings())
    assert result["written"] == 3
    assert len(fake_s3.objects) == 3


def test_pipeline_promotes_bronze_to_gold(monkeypatch: Any) -> None:
    fake_s3 = FakeS3()
    fake_ddb = FakeDDB()
    event = CommerceEvent(
        event_id="evt-1",
        event_ts=datetime(2026, 1, 2, tzinfo=UTC),
        event_type="purchase",
        user_id="user-1",
        sku="SKU-100",
        quantity=1,
        amount_usd=10.0,
        country="US",
    )
    fake_s3.put_object(
        Bucket="b",
        Key=bronze_key(event),
        Body=event.model_dump_json().encode("utf-8"),
    )

    def _client(service: str, settings: Settings | None = None) -> Any:
        return fake_s3 if service == "s3" else fake_ddb

    monkeypatch.setattr("lakehouse.ops.pipeline.client", _client)
    result = run_pipeline(settings=_settings())
    assert result["bronze_objects"] == 1
    assert result["silver_written"] == 1
    assert result["gold_written"] == 1
    assert any(key[0] == "g" for key in fake_s3.objects)
