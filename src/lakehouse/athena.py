"""Athena workgroup and named analytical queries.

MiniStack rarely emulates Athena. Specs live here so Terraform
(``infra/terraform/athena.tf``), the CLI, and tests stay aligned. Local
``register_athena`` / ``run_named_query`` describe the SQL and try the
Athena API; they fall back to ``backend=spec`` when the service is missing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from lakehouse.catalog import GLUE_DATABASE, GOLD_TABLE, SILVER_TABLE
from lakehouse.config import Settings, load_settings

WORKGROUP = "lakehouse-local"
RESULT_PREFIX = "athena-results/"


@dataclass(frozen=True, slots=True)
class NamedQuery:
    name: str
    description: str
    database: str
    sql: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def workgroup_name() -> str:
    return WORKGROUP


def result_location(settings: Settings | None = None) -> str:
    resolved = settings or load_settings()
    bucket = resolved.gold_bucket
    return f"s3://{bucket}/{RESULT_PREFIX}"


def named_queries() -> tuple[NamedQuery, ...]:
    db = GLUE_DATABASE
    gold = f"{db}.{GOLD_TABLE}"
    silver = f"{db}.{SILVER_TABLE}"
    return (
        NamedQuery(
            name="gold_daily_totals",
            description="All Gold daily event metrics ordered by date then metric.",
            database=db,
            sql=(f"SELECT metric, dt, events, amount_usd\nFROM {gold}\nORDER BY dt, metric;"),
        ),
        NamedQuery(
            name="gold_purchase_revenue",
            description="Purchase-only Gold rows (revenue proxy).",
            database=db,
            sql=(
                f"SELECT dt, events, amount_usd\n"
                f"FROM {gold}\n"
                f"WHERE metric = 'purchase'\n"
                f"ORDER BY dt;"
            ),
        ),
        NamedQuery(
            name="gold_last_7_days",
            description="Gold metrics for the last 7 calendar days (inclusive).",
            database=db,
            sql=(
                f"SELECT metric, dt, events, amount_usd\n"
                f"FROM {gold}\n"
                f"WHERE dt >= date_format(date_add('day', -6, current_date), '%Y-%m-%d')\n"
                f"ORDER BY dt, metric;"
            ),
        ),
        NamedQuery(
            name="silver_late_event_counts",
            description="Count of late vs on-time Silver events by type and day.",
            database=db,
            sql=(
                f"SELECT event_type, dt,\n"
                f"       count(*) AS events,\n"
                f"       sum(CASE WHEN _late THEN 1 ELSE 0 END) AS late_events\n"
                f"FROM {silver}\n"
                f"GROUP BY event_type, dt\n"
                f"ORDER BY dt, event_type;"
            ),
        ),
    )


def get_named_query(name: str) -> NamedQuery:
    for item in named_queries():
        if item.name == name:
            return item
    known = ", ".join(q.name for q in named_queries())
    raise KeyError(f"unknown named query {name!r}; expected one of: {known}")


def workgroup_config(settings: Settings | None = None) -> dict[str, Any]:
    resolved = settings or load_settings()
    return {
        "name": WORKGROUP,
        "description": "Medallion lakehouse analyst workgroup with scan caps.",
        "state": "ENABLED",
        "result_location": result_location(resolved),
        "bytes_scanned_cutoff_per_query": 100 * 1024 * 1024,
        "enforce_workgroup_configuration": True,
        "publish_cloudwatch_metrics": True,
        "database": GLUE_DATABASE,
        "named_queries": [q.as_dict() for q in named_queries()],
    }


def _ensure_workgroup(athena: Any, settings: Settings) -> str:
    name = WORKGROUP
    config = {
        "ResultConfiguration": {"OutputLocation": result_location(settings)},
        "EnforceWorkGroupConfiguration": True,
        "PublishCloudWatchMetricsEnabled": True,
        "BytesScannedCutoffPerQuery": 100 * 1024 * 1024,
    }
    try:
        athena.get_work_group(WorkGroup=name)
        athena.update_work_group(
            WorkGroup=name,
            Description="Medallion lakehouse analyst workgroup with scan caps.",
            ConfigurationUpdates={
                "ResultConfigurationUpdates": {
                    "OutputLocation": result_location(settings),
                },
                "EnforceWorkGroupConfiguration": True,
                "PublishCloudWatchMetricsEnabled": True,
                "BytesScannedCutoffPerQuery": 100 * 1024 * 1024,
            },
        )
        return "updated"
    except Exception:
        athena.create_work_group(
            Name=name,
            Description="Medallion lakehouse analyst workgroup with scan caps.",
            Configuration=config,
        )
        return "created"


def _put_named_query(athena: Any, query: NamedQuery) -> str:
    existing = athena.list_named_queries(WorkGroup=WORKGROUP)
    ids = existing.get("NamedQueryIds") or []
    for qid in ids:
        detail = athena.get_named_query(NamedQueryId=qid)
        body = detail.get("NamedQuery") or {}
        if body.get("Name") == query.name:
            return "exists"
    athena.create_named_query(
        Name=query.name,
        Description=query.description,
        Database=query.database,
        QueryString=query.sql,
        WorkGroup=WORKGROUP,
    )
    return "created"


def register_athena(settings: Settings | None = None) -> dict[str, Any]:
    """Create/update the workgroup and named queries. Falls back to specs."""

    resolved = settings or load_settings()
    result: dict[str, Any] = {
        "workgroup": workgroup_config(resolved),
        "backend": "athena",
        "actions": {},
        "errors": [],
    }
    try:
        from lakehouse.aws import client

        athena = client("athena", resolved)
        result["actions"]["workgroup"] = _ensure_workgroup(athena, resolved)
        for query in named_queries():
            result["actions"][query.name] = _put_named_query(athena, query)
    except Exception as exc:
        result["backend"] = "spec"
        result["errors"].append(str(exc))
        result["actions"] = {
            "workgroup": "described",
            **{q.name: "described" for q in named_queries()},
        }
    return result


def run_named_query(
    name: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Start a named query on Athena when available; otherwise return SQL."""

    resolved = settings or load_settings()
    query = get_named_query(name)
    payload: dict[str, Any] = {
        "name": query.name,
        "sql": query.sql,
        "database": query.database,
        "workgroup": WORKGROUP,
        "backend": "athena",
        "execution_id": None,
        "errors": [],
    }
    try:
        from lakehouse.aws import client

        athena = client("athena", resolved)
        started = athena.start_query_execution(
            QueryString=query.sql,
            QueryExecutionContext={"Database": query.database},
            WorkGroup=WORKGROUP,
            ResultConfiguration={"OutputLocation": result_location(resolved)},
        )
        payload["execution_id"] = started.get("QueryExecutionId")
    except Exception as exc:
        payload["backend"] = "spec"
        payload["errors"].append(str(exc))
    return payload
