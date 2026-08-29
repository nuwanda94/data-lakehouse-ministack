from __future__ import annotations

from pathlib import Path

from lakehouse.ops.notify import (
    BRONZE_NOTIFY_EVENTS,
    BRONZE_NOTIFY_PREFIX,
    expected_notification,
    notification_matches,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTIFY_TF = REPO_ROOT / "infra" / "terraform" / "notifications.tf"


def test_expected_notification_targets_events_prefix() -> None:
    spec = expected_notification(queue_arn="arn:aws:sqs:us-east-1:000000000000:q")
    queue = spec["QueueConfigurations"][0]
    assert queue["Events"] == list(BRONZE_NOTIFY_EVENTS)
    assert queue["Filter"]["Key"]["FilterRules"][0]["Value"] == BRONZE_NOTIFY_PREFIX
    assert "EventBridgeConfiguration" in spec


def test_notification_matches_accepts_live_shape() -> None:
    arn = "arn:aws:sqs:us-east-1:000000000000:lakehouse-local-bronze-events"
    live = {
        "QueueConfigurations": [
            {
                "Id": "bronze-events-sqs",
                "QueueArn": arn,
                "Events": ["s3:ObjectCreated:*"],
                "Filter": {"Key": {"FilterRules": [{"Name": "Prefix", "Value": "events/"}]}},
            }
        ]
    }
    assert notification_matches(live, queue_arn=arn)
    assert not notification_matches({"QueueConfigurations": []}, queue_arn=arn)
    assert not notification_matches(
        {
            "QueueConfigurations": [
                {
                    "QueueArn": arn,
                    "Events": ["s3:ObjectRemoved:*"],
                    "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "events/"}]}},
                }
            ]
        },
        queue_arn=arn,
    )


def test_terraform_wires_bronze_object_created_to_sqs() -> None:
    text = NOTIFY_TF.read_text(encoding="utf-8")
    assert "aws_s3_bucket_notification" in text
    assert "aws_sqs_queue_policy" in text
    assert "s3:ObjectCreated:*" in text
    assert 'filter_prefix = "events/"' in text
    assert "eventbridge = true" in text
    assert "sqs:SendMessage" in text
