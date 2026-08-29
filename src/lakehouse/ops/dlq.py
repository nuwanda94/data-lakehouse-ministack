"""Dead-letter queue inspection and redrive for Bronze events.

The Terraform Bronze queue uses a redrive policy
(``maxReceiveCount`` → ``bronze_events_dlq``). MiniStack may not always
honor that policy, so this module also:

* leaves failed local drains on the source queue (so a real DLQ can fire)
* can copy poison messages onto the DLQ explicitly
* can redrive DLQ messages back onto the source queue
"""

from __future__ import annotations

import json
from typing import Any

from lakehouse.aws import client
from lakehouse.config import Settings, load_settings

DEFAULT_BATCH = 10


def resolve_queue_url(
    sqs: Any,
    *,
    name: str,
    explicit_url: str = "",
) -> str:
    """Return a queue URL, preferring an explicit setting over GetQueueUrl."""

    if explicit_url:
        return explicit_url
    resp = sqs.get_queue_url(QueueName=name)
    return str(resp["QueueUrl"])


def source_and_dlq_urls(
    settings: Settings,
    sqs: Any | None = None,
) -> tuple[str, str]:
    """Resolve (source queue URL, DLQ URL)."""

    sqs_client = sqs or client("sqs", settings)
    source = resolve_queue_url(
        sqs_client,
        name=settings.bronze_events_queue,
        explicit_url=settings.bronze_events_queue_url,
    )
    dlq = resolve_queue_url(
        sqs_client,
        name=settings.bronze_events_dlq,
        explicit_url=settings.bronze_events_dlq_url,
    )
    return source, dlq


def _summarize(message: dict[str, Any]) -> dict[str, Any]:
    body = message.get("Body") or ""
    preview = body if len(body) <= 240 else body[:237] + "..."
    attrs = message.get("Attributes") or {}
    return {
        "message_id": message.get("MessageId"),
        "receipt_handle": message.get("ReceiptHandle"),
        "approximate_receive_count": attrs.get("ApproximateReceiveCount"),
        "body_preview": preview,
        "body_bytes": len(body.encode("utf-8")),
    }


def peek_messages(
    sqs: Any,
    queue_url: str,
    *,
    max_messages: int = DEFAULT_BATCH,
    wait_seconds: int = 0,
    visibility_timeout: int = 30,
) -> list[dict[str, Any]]:
    """Receive a batch without deleting (visibility timeout still applies)."""

    received = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=min(max(max_messages, 1), 10),
        WaitTimeSeconds=wait_seconds,
        VisibilityTimeout=visibility_timeout,
        AttributeNames=["All"],
    )
    return list(received.get("Messages") or [])


def list_dlq(
    *,
    settings: Settings | None = None,
    sqs: Any | None = None,
    max_messages: int = DEFAULT_BATCH,
) -> dict[str, Any]:
    """Peek the Bronze DLQ and return message summaries."""

    resolved = settings or load_settings()
    sqs_client = sqs or client("sqs", resolved)
    _, dlq_url = source_and_dlq_urls(resolved, sqs_client)
    messages = peek_messages(sqs_client, dlq_url, max_messages=max_messages)
    return {
        "queue": resolved.bronze_events_dlq,
        "queue_url": dlq_url,
        "polled": len(messages),
        "messages": [_summarize(msg) for msg in messages],
    }


def move_messages(
    sqs: Any,
    *,
    source_url: str,
    dest_url: str,
    max_messages: int = DEFAULT_BATCH,
    wait_seconds: int = 1,
    delete_source: bool = True,
) -> dict[str, Any]:
    """Copy a batch from ``source_url`` to ``dest_url`` and optionally delete."""

    messages = peek_messages(
        sqs,
        source_url,
        max_messages=max_messages,
        wait_seconds=wait_seconds,
        visibility_timeout=60,
    )
    moved: list[str] = []
    errors: list[str] = []
    for message in messages:
        body = message.get("Body") or ""
        message_id = message.get("MessageId") or ""
        try:
            sqs.send_message(QueueUrl=dest_url, MessageBody=body)
        except Exception as exc:  # noqa: BLE001 — surface service errors to the CLI
            errors.append(f"{message_id}: {exc}")
            continue
        moved.append(message_id)
        receipt = message.get("ReceiptHandle")
        if delete_source and receipt:
            sqs.delete_message(QueueUrl=source_url, ReceiptHandle=receipt)
    return {
        "polled": len(messages),
        "moved": len(moved),
        "message_ids": moved,
        "errors": errors,
        "source_url": source_url,
        "dest_url": dest_url,
    }


def redrive_dlq(
    *,
    settings: Settings | None = None,
    sqs: Any | None = None,
    max_messages: int = DEFAULT_BATCH,
    wait_seconds: int = 1,
) -> dict[str, Any]:
    """Move messages from the Bronze DLQ back onto the source events queue."""

    resolved = settings or load_settings()
    sqs_client = sqs or client("sqs", resolved)
    source_url, dlq_url = source_and_dlq_urls(resolved, sqs_client)
    result = move_messages(
        sqs_client,
        source_url=dlq_url,
        dest_url=source_url,
        max_messages=max_messages,
        wait_seconds=wait_seconds,
        delete_source=True,
    )
    result["source_queue"] = resolved.bronze_events_dlq
    result["dest_queue"] = resolved.bronze_events_queue
    return result


def quarantine_to_dlq(
    *,
    settings: Settings | None = None,
    sqs: Any | None = None,
    body: str,
) -> dict[str, Any]:
    """Send a poison payload to the DLQ (local MiniStack / tests)."""

    resolved = settings or load_settings()
    sqs_client = sqs or client("sqs", resolved)
    _, dlq_url = source_and_dlq_urls(resolved, sqs_client)
    resp = sqs_client.send_message(QueueUrl=dlq_url, MessageBody=body)
    return {
        "queue": resolved.bronze_events_dlq,
        "queue_url": dlq_url,
        "message_id": resp.get("MessageId"),
    }


def encode_event(event: dict[str, Any]) -> str:
    """Serialize an ingest event so it can live on SQS."""

    return json.dumps(event, default=str)
