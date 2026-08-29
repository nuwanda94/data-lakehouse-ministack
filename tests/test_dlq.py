from __future__ import annotations

from typing import Any

from lakehouse.config import Settings
from lakehouse.ops.dlq import list_dlq, move_messages, redrive_dlq, resolve_queue_url


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
        bronze_events_queue="bronze-events",
        bronze_events_queue_url="http://sqs/bronze-events",
        bronze_events_dlq="bronze-events-dlq",
        bronze_events_dlq_url="http://sqs/bronze-events-dlq",
    )


class FakeSqs:
    def __init__(self) -> None:
        self.queues: dict[str, list[dict[str, Any]]] = {
            "http://sqs/bronze-events": [],
            "http://sqs/bronze-events-dlq": [],
        }
        self.deleted: list[str] = []
        self.sent: list[tuple[str, str]] = []
        self._seq = 0

    def get_queue_url(self, **kwargs: Any) -> dict[str, str]:
        name = kwargs["QueueName"]
        return {"QueueUrl": f"http://sqs/{name}"}

    def send_message(self, **kwargs: Any) -> dict[str, str]:
        self._seq += 1
        mid = f"m{self._seq}"
        url = kwargs["QueueUrl"]
        body = kwargs["MessageBody"]
        self.queues.setdefault(url, []).append(
            {
                "MessageId": mid,
                "ReceiptHandle": f"r{self._seq}",
                "Body": body,
                "Attributes": {"ApproximateReceiveCount": "1"},
            }
        )
        self.sent.append((url, body))
        return {"MessageId": mid}

    def receive_message(self, **kwargs: Any) -> dict[str, Any]:
        url = kwargs["QueueUrl"]
        limit = int(kwargs.get("MaxNumberOfMessages") or 10)
        batch = list(self.queues.get(url, [])[:limit])
        return {"Messages": batch}

    def delete_message(self, **kwargs: Any) -> dict[str, Any]:
        url = kwargs["QueueUrl"]
        handle = kwargs["ReceiptHandle"]
        self.deleted.append(handle)
        self.queues[url] = [m for m in self.queues.get(url, []) if m.get("ReceiptHandle") != handle]
        return {}


def test_resolve_queue_url_prefers_explicit() -> None:
    sqs = FakeSqs()
    assert resolve_queue_url(sqs, name="x", explicit_url="http://explicit") == "http://explicit"
    assert resolve_queue_url(sqs, name="bronze-events-dlq") == "http://sqs/bronze-events-dlq"


def test_list_dlq_summarizes_bodies() -> None:
    sqs = FakeSqs()
    sqs.send_message(QueueUrl="http://sqs/bronze-events-dlq", MessageBody='{"poison":true}')
    result = list_dlq(settings=_settings(), sqs=sqs)
    assert result["polled"] == 1
    assert result["queue"] == "bronze-events-dlq"
    assert result["messages"][0]["body_preview"].startswith("{")


def test_redrive_moves_and_deletes() -> None:
    sqs = FakeSqs()
    sqs.send_message(QueueUrl="http://sqs/bronze-events-dlq", MessageBody="retry-me")
    result = redrive_dlq(settings=_settings(), sqs=sqs)
    assert result["moved"] == 1
    assert result["dest_queue"] == "bronze-events"
    assert sqs.queues["http://sqs/bronze-events-dlq"] == []
    assert sqs.queues["http://sqs/bronze-events"][0]["Body"] == "retry-me"


def test_move_messages_reports_send_errors() -> None:
    class BrokenSend(FakeSqs):
        def send_message(self, **kwargs: Any) -> dict[str, str]:
            raise RuntimeError("denied")

    sqs = BrokenSend()
    sqs.queues["http://sqs/src"] = [
        {"MessageId": "m1", "ReceiptHandle": "r1", "Body": "x", "Attributes": {}}
    ]
    result = move_messages(
        sqs,
        source_url="http://sqs/src",
        dest_url="http://sqs/dst",
    )
    assert result["moved"] == 0
    assert result["errors"]
    assert sqs.queues["http://sqs/src"]  # not deleted after send failure
