"""Step Functions definition and a local interpreter of the same graph.

The ASL graph is the Phase 2 control plane described in ADR-003:

    IngestBronze → TransformSilver → QualityGate → Choice
        passed  → AggregateGold → Succeeded
        failed  → QualityFailed
    any Task error → Failed

``run_sfn_local`` walks that graph by calling the same zone handlers the
Lambdas use, so MiniStack does not need a working Step Functions service
for the inner loop. Terraform still deploys ``aws_sfn_state_machine`` for
real AWS / MiniStack SFN.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

LAMBDA_INVOKE = "arn:aws:states:::lambda:invoke"

STATE_ORDER = (
    "IngestBronze",
    "TransformSilver",
    "QualityGate",
    "QualityChoice",
    "AggregateGold",
    "Succeeded",
    "QualityFailed",
    "Failed",
)

DEFAULT_RETRY = [
    {
        "ErrorEquals": [
            "States.TaskFailed",
            "Lambda.ServiceException",
            "Lambda.TooManyRequestsException",
        ],
        "IntervalSeconds": 2,
        "MaxAttempts": 3,
        "BackoffRate": 2.0,
    }
]


def _task(
    *,
    function_arn: str,
    result_path: str,
    next_state: str,
    comment: str,
) -> dict[str, Any]:
    return {
        "Type": "Task",
        "Comment": comment,
        "Resource": LAMBDA_INVOKE,
        "Parameters": {
            "FunctionName": function_arn,
            "Payload.$": "$",
        },
        "ResultSelector": {
            "status.$": "$.Payload.status",
            "run_id.$": "$.Payload.run_id",
            "passed.$": "$.Payload.passed",
            "error.$": "$.Payload.error",
            "metrics.$": "$.Payload.metrics",
        },
        "ResultPath": result_path,
        "Retry": DEFAULT_RETRY,
        "Catch": [
            {
                "ErrorEquals": ["States.ALL"],
                "ResultPath": "$.error",
                "Next": "Failed",
            }
        ],
        "Next": next_state,
    }


def build_definition(
    *,
    ingest_arn: str = "${ingest_arn}",
    silver_arn: str = "${silver_arn}",
    quality_arn: str = "${quality_arn}",
    gold_arn: str = "${gold_arn}",
) -> dict[str, Any]:
    """Return the Amazon States Language definition for the medallion run."""

    return {
        "Comment": "Medallion lakehouse: Bronze ingest → Silver → quality gate → Gold",
        "StartAt": "IngestBronze",
        "States": {
            "IngestBronze": _task(
                function_arn=ingest_arn,
                result_path="$.ingest",
                next_state="TransformSilver",
                comment="HEAD/GET Bronze objects and record the run",
            ),
            "TransformSilver": _task(
                function_arn=silver_arn,
                result_path="$.silver",
                next_state="QualityGate",
                comment="Cleanse Bronze JSON into Silver + quarantine",
            ),
            "QualityGate": _task(
                function_arn=quality_arn,
                result_path="$.quality",
                next_state="QualityChoice",
                comment="Named quality checks; fail or quarantine",
            ),
            "QualityChoice": {
                "Type": "Choice",
                "Comment": "Stop the run when the gate fails; otherwise aggregate Gold",
                "Choices": [
                    {
                        "Or": [
                            {
                                "Variable": "$.quality.passed",
                                "BooleanEquals": False,
                            },
                            {
                                "Variable": "$.quality.status",
                                "StringEquals": "quality_failed",
                            },
                        ],
                        "Next": "QualityFailed",
                    }
                ],
                "Default": "AggregateGold",
            },
            "AggregateGold": _task(
                function_arn=gold_arn,
                result_path="$.gold",
                next_state="Succeeded",
                comment="Daily Gold metrics + DynamoDB rows",
            ),
            "Succeeded": {
                "Type": "Succeed",
                "Comment": "Full Bronze → Gold pass completed",
            },
            "QualityFailed": {
                "Type": "Fail",
                "Error": "QualityGateFailed",
                "Cause": "Silver quality gate rejected the run",
            },
            "Failed": {
                "Type": "Fail",
                "Error": "PipelineFailed",
                "Cause": "A zone Lambda raised; see $.error",
            },
        },
    }


def definition_json(**kwargs: str) -> str:
    """Pretty-printed ASL JSON."""

    return json.dumps(build_definition(**kwargs), indent=2) + "\n"


def _status_of(step: dict[str, Any] | None) -> str:
    if not step:
        return "unknown"
    return str(step.get("status") or "unknown")


def run_sfn_local(
    event: dict[str, Any] | None = None,
    *,
    ingest: Callable[..., dict[str, Any]] | None = None,
    silver: Callable[..., dict[str, Any]] | None = None,
    quality: Callable[..., dict[str, Any]] | None = None,
    gold: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Interpret the SFN graph locally by calling zone handlers in order.

    Handlers may be injected for tests. Defaults import the production
    Lambda wrappers.
    """

    if ingest is None:
        from lakehouse.ingest.bronze_handler import ingest_bronze_event as ingest
    if silver is None:
        from lakehouse.silver.handler import transform_silver as silver
    if quality is None:
        from lakehouse.quality.handler import run_quality_gate as quality
    if gold is None:
        from lakehouse.gold.handler import transform_gold as gold

    payload: dict[str, Any] = dict(event or {})
    history: list[str] = []

    def _call(name: str, path: str, fn: Callable[..., dict[str, Any]]) -> dict[str, Any]:
        history.append(name)
        try:
            result = fn(payload)
        except Exception as exc:  # noqa: BLE001
            history.append("Failed")
            return {
                "status": "failed",
                "terminal": "Failed",
                "error": str(exc),
                "history": history,
                "state": payload,
            }
        if not isinstance(result, dict):
            result = {"status": "succeeded", "result": result}
        payload[path] = result
        return result

    ingest_result = _call("IngestBronze", "ingest", ingest)
    if ingest_result.get("status") == "failed" or ingest_result.get("terminal") == "Failed":
        if ingest_result.get("terminal") == "Failed":
            return ingest_result
        history.append("Failed")
        return {
            "status": "failed",
            "terminal": "Failed",
            "error": ingest_result.get("error"),
            "history": history,
            "ingest": ingest_result,
            "state": payload,
        }

    silver_result = _call("TransformSilver", "silver", silver)
    if silver_result.get("terminal") == "Failed":
        return silver_result
    if _status_of(silver_result) == "failed":
        history.append("Failed")
        return {
            "status": "failed",
            "terminal": "Failed",
            "error": silver_result.get("error"),
            "history": history,
            "silver": silver_result,
            "state": payload,
        }

    quality_result = _call("QualityGate", "quality", quality)
    if quality_result.get("terminal") == "Failed":
        return quality_result
    history.append("QualityChoice")
    failed_gate = (quality_result.get("passed") is False) or (
        _status_of(quality_result) == "quality_failed"
    )
    if failed_gate:
        history.append("QualityFailed")
        return {
            "status": "quality_failed",
            "terminal": "QualityFailed",
            "error": quality_result.get("error"),
            "history": history,
            "quality": quality_result,
            "state": payload,
        }

    gold_result = _call("AggregateGold", "gold", gold)
    if gold_result.get("terminal") == "Failed":
        return gold_result
    if _status_of(gold_result) == "failed":
        history.append("Failed")
        return {
            "status": "failed",
            "terminal": "Failed",
            "error": gold_result.get("error"),
            "history": history,
            "gold": gold_result,
            "state": payload,
        }

    history.append("Succeeded")
    run_id = (
        gold_result.get("run_id")
        or quality_result.get("run_id")
        or silver_result.get("run_id")
        or ingest_result.get("run_id")
    )
    return {
        "status": "succeeded",
        "terminal": "Succeeded",
        "run_id": run_id,
        "history": history,
        "ingest": ingest_result,
        "silver": silver_result,
        "quality": quality_result,
        "gold": gold_result,
    }
