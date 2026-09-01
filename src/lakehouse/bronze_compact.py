"""Bronze raw-object compact / rewrite policy.

MiniStack CI is hermetic, so this module always evaluates a spec snapshot
(Bronze Hive ``events/dt=`` keys vs a max-objects threshold) and
optionally folds in live S3 objects when MiniStack answers.

Seed and ingest write one JSON object per event. Compaction rewrites a
fragmented day prefix into a single ``part-000.json`` and drops the
siblings. ``python -m lakehouse bronze-compact`` prints JSON. Default is
dry-run (``apply=false``). Exit code 1 means compact was requested and a
rewrite or delete failed.

Max objects per partition comes from
``LAKEHOUSE_BRONZE_COMPACT_MAX_OBJECTS`` (default 8) or ``--max-objects``.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

from lakehouse.config import Settings, load_settings
from lakehouse.partitions import parse_hive_key

DEFAULT_MAX_OBJECTS = 8
DATASET_ID = "bronze.raw_events"
PREFIX = "events/"
COMPACT_NAME = "part-000.json"
