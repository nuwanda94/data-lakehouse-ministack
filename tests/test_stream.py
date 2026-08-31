from __future__ import annotations

import json

from lakehouse.cli import main
from lakehouse.seed.generate import generate_events
from lakehouse.stream import (
    decode_stream_payload,
    deliver_firehose_batch,
    encode_firehose_record,
    encode_kinesis_record,
    run_stream,
)


def test_encode_round_trip() -> None:
    event = generate_events(1)[0]
    kinesis = encode_kinesis_record(event)
    firehose = encode_firehose_record(event)
    assert kinesis["PartitionKey"] == event.user_id
    decoded_k = decode_stream_payload(kinesis["Data"])
    decoded_f = decode_stream_payload(firehose["Data"])
    assert decoded_k["event_id"] == event.event_id
    assert decoded_f["event_id"] == event.event_id
    assert decoded_k["sku"] == event.sku


def test_firehose_delivery_uses_bronze_keys() -> None:
    events = generate_events(3)
    delivered = deliver_firehose_batch(events)
    assert len(delivered) == 3
    assert delivered[0]["key"].startswith("events/dt=")
    assert delivered[0]["key"].endswith(".json")


def test_offline_stream_both_sinks() -> None:
    result = run_stream(5, mode="offline", sink="both")
    assert result["ok"] is True
    assert result["backend"] == "offline"
    assert result["produced"] == 5
    assert result["kinesis_records"] == 5
    assert result["firehose_records"] == 5
    assert len(result["bronze_objects"]) == 5
    assert len(result["decoded_event_ids"]) == 5


def test_offline_stream_kinesis_only() -> None:
    result = run_stream(2, mode="offline", sink="kinesis")
    assert result["kinesis_records"] == 2
    assert result["firehose_records"] == 0


def test_cli_stream_offline(capsys: object) -> None:
    assert main(["stream", "--mode", "offline", "--count", "4", "--sink", "firehose"]) == 0
    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert payload["ok"] is True
    assert payload["backend"] == "offline"
    assert payload["produced"] == 4
    assert payload["firehose_records"] == 4
