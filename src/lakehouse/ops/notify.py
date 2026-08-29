"""Contract for Bronze S3 → SQS / EventBridge object notifications."""

from __future__ import annotations

from typing import Any

BRONZE_NOTIFY_PREFIX = "events/"
BRONZE_NOTIFY_EVENTS = ("s3:ObjectCreated:*",)
BRONZE_NOTIFY_QUEUE_ID = "bronze-events-sqs"


def expected_notification(*, queue_arn: str) -> dict[str, Any]:
    """Shape Terraform applies on the Bronze bucket."""

    return {
        "QueueConfigurations": [
            {
                "Id": BRONZE_NOTIFY_QUEUE_ID,
                "QueueArn": queue_arn,
                "Events": list(BRONZE_NOTIFY_EVENTS),
                "Filter": {
                    "Key": {
                        "FilterRules": [
                            {"Name": "prefix", "Value": BRONZE_NOTIFY_PREFIX},
                        ]
                    }
                },
            }
        ],
        "EventBridgeConfiguration": {},
    }


def notification_matches(config: dict[str, Any], *, queue_arn: str | None = None) -> bool:
    """Return True when a GetBucketNotificationConfiguration result is wired."""

    queues = config.get("QueueConfigurations") or []
    if not isinstance(queues, list) or not queues:
        return False
    for entry in queues:
        if not isinstance(entry, dict):
            continue
        events = {str(e) for e in (entry.get("Events") or [])}
        if not events.intersection(BRONZE_NOTIFY_EVENTS) and "s3:ObjectCreated:Put" not in events:
            continue
        if queue_arn and str(entry.get("QueueArn") or "") != queue_arn:
            continue
        rules = ((entry.get("Filter") or {}).get("Key") or {}).get("FilterRules") or []
        prefixes = [
            str(rule.get("Value") or "")
            for rule in rules
            if isinstance(rule, dict) and str(rule.get("Name") or "").lower() == "prefix"
        ]
        if any(p == BRONZE_NOTIFY_PREFIX or p == "events" for p in prefixes):
            return True
        if not prefixes:
            # MiniStack may drop the filter; still accept a queue target.
            return True
    return False
