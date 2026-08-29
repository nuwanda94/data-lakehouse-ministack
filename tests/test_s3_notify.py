from __future__ import annotations

from pathlib import Path

from lakehouse.ops.notify import (
    BRONZE_NOTIFY_EVENTS,
    BRONZE_NOTIFY_PREFIX,
    expected_notification,
    notification_matches,
)


def test_expected_notification_shape() -> None:
    n = expected_notification(bucket="lakehouse-local-bronze")
    assert n["Id"]
    assert n["Events"] == BRONZE_NOTIFY_EVENTS
    assert n["Filter"]["Key"]["FilterRules"][0]["Value"] == BRONZE_NOTIFY_PREFIX


def test_notification_matches_accepts_equivalent() -> None:
    expected = expected_notification(bucket="lakehouse-local-bronze")
    actual = dict(expected)
    assert notification_matches(actual, expected)


def test_notification_matches_rejects_different_prefix() -> None:
    expected = expected_notification(bucket="lakehouse-local-bronze")
    actual = expected_notification(bucket="lakehouse-local-bronze")
    actual["Filter"]["Key"]["FilterRules"][0]["Value"] = "other/"
    assert not notification_matches(actual, expected)


def test_terraform_notifications_present() -> None:
    tf = Path("infra/terraform/notifications.tf")
    text = tf.read_text(encoding="utf-8")
    assert "aws_s3_bucket_notification" in text
    assert "bronze_events" in text or "bronze" in text.lower()
