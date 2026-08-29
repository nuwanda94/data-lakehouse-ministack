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
