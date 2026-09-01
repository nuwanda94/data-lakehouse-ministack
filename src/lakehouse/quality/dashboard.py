"""Data-quality dashboard / summary for the Silver gate.

MiniStack CI is hermetic, so this module:

* always evaluates the named quality checks against a small fixture batch
* optionally folds in live Silver ``quality/`` reports and pipeline-run rows
* renders a self-contained HTML summary (no Streamlit)

``python -m lakehouse quality-dashboard --out build/quality-dashboard.html``
writes the page. Live AWS failures fall back to the spec snapshot.
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lakehouse.config import Settings, load_settings
from lakehouse.quality.gate import evaluate_quality
from lakehouse.seed.generate import generate_events

CHECK_NAMES = (
    "event_id_present",
    "known_event_type",
    "required_dimensions",
    "quantity_and_amount_sane",
    "schema_valid",
)


def _sample_records() -> list[dict[str, Any]]:
    """Good seed events plus a few poison rows so the spec view is not empty."""

    good = [e.model_dump(mode="json") for e in generate_events(8)]
    bad: list[dict[str, Any]] = [
        {
            "event_id": "",
            "event_ts": "2026-09-01T00:00:00+00:00",
            "event_type": "purchase",
            "user_id": "u-1",
            "sku": "sku-1",
            "quantity": 1,
            "amount_usd": 9.0,
            "country": "US",
        },
        {
            "event_id": "e-unknown",
            "event_ts": "2026-09-01T00:00:00+00:00",
            "event_type": "not_an_event",
            "user_id": "u-2",
            "sku": "sku-2",
            "quantity": 1,
            "amount_usd": 3.0,
            "country": "US",
        },
        {
            "event_id": "e-neg",
            "event_ts": "2026-09-01T00:00:00+00:00",
            "event_type": "purchase",
            "user_id": "u-3",
            "sku": "sku-3",
            "quantity": 0,
            "amount_usd": -1.0,
            "country": "US",
        },
    ]
    return good + bad


def spec_summary() -> dict[str, Any]:
    """Offline quality snapshot used by unit tests and when MiniStack is down."""

    decision = evaluate_quality(_sample_records(), on_fail="quarantine", max_fail_ratio=0.0)
    return {
        "source": "spec",
        "passed": decision.passed,
        "action": decision.action,
        "rows_scanned": decision.rows_scanned,
        "rows_failed": decision.rows_failed,
        "fail_ratio": round(decision.fail_ratio, 4),
        "checks": [r.model_dump() for r in decision.results],
        "failed_reasons": [
            {"event_id": row.payload.get("event_id") or "", "reasons": row.reasons}
            for row in decision.failed_rows
        ],
    }


def _load_live_reports(settings: Settings) -> tuple[list[dict[str, Any]], list[str]]:
    reports: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        from lakehouse.aws import client

        s3 = client("s3", settings)
        token: str | None = None
        keys: list[str] = []
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": settings.silver_bucket,
                "Prefix": "quality/",
            }
            if token:
                kwargs["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []) or []:
                key = obj.get("Key") or ""
                if key and not key.endswith("/"):
                    keys.append(key)
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        for key in keys[-20:]:
            body = s3.get_object(Bucket=settings.silver_bucket, Key=key)["Body"].read()
            text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
            payload = json.loads(text)
            if isinstance(payload, dict):
                payload["report_key"] = key
                reports.append(payload)
    except Exception as exc:  # MiniStack / bucket may be absent in unit CI
        errors.append(f"reports: {exc}")
    return reports, errors


def _load_live_runs(settings: Settings) -> tuple[list[dict[str, Any]], list[str]]:
    runs: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        from lakehouse.ops.runs import query_runs

        payload = query_runs(settings=settings, limit=15)
        for row in payload.get("runs") or []:
            if not isinstance(row, dict):
                continue
            runs.append(
                {
                    "run_id": row.get("run_id"),
                    "status": row.get("status"),
                    "started_at": row.get("started_at"),
                    "error": row.get("error"),
                }
            )
    except Exception as exc:
        errors.append(f"runs: {exc}")
    return runs, errors


def collect_snapshot(*, settings: Settings | None = None) -> dict[str, Any]:
    """Build a JSON-serializable quality dashboard snapshot."""

    errors: list[str] = []
    resolved = settings
    if resolved is None:
        try:
            resolved = load_settings()
        except Exception as exc:
            errors.append(f"settings: {exc}")
            resolved = None

    spec = spec_summary()
    snapshot: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "silver_bucket": getattr(resolved, "silver_bucket", "lakehouse-local-silver"),
        "pipeline_runs_table": getattr(
            resolved, "pipeline_runs_table", "lakehouse-local-pipeline-runs"
        ),
        "backend": "spec" if resolved is None else "live",
        "check_names": list(CHECK_NAMES),
        "spec": spec,
        "reports": [],
        "runs": [],
        "errors": list(errors),
    }
    if resolved is None:
        return snapshot

    reports, report_errors = _load_live_reports(resolved)
    runs, run_errors = _load_live_runs(resolved)
    snapshot["reports"] = reports
    snapshot["runs"] = runs
    snapshot["errors"].extend(report_errors)
    snapshot["errors"].extend(run_errors)
    if snapshot["errors"]:
        snapshot["backend"] = "spec"
    return snapshot


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _rows_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "<p class='empty'>No rows.</p>"
    head = "".join(f"<th>{_esc(col)}</th>" for col in columns)
    body_parts: list[str] = []
    for row in rows:
        cells = "".join(f"<td>{_esc(row.get(col))}</td>" for col in columns)
        body_parts.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"


def render_html(snapshot: dict[str, Any] | None = None) -> str:
    data = snapshot or collect_snapshot()
    spec = dict(data.get("spec") or {})
    checks = list(spec.get("checks") or [])
    reasons = list(spec.get("failed_reasons") or [])
    reports = list(data.get("reports") or [])
    runs = list(data.get("runs") or [])
    errors = list(data.get("errors") or [])

    check_rows = [
        {
            "check_name": c.get("check_name"),
            "passed": c.get("passed"),
            "rows_scanned": c.get("rows_scanned"),
            "rows_failed": c.get("rows_failed"),
        }
        for c in checks
    ]
    reason_rows = [
        {"event_id": r.get("event_id"), "reasons": ",".join(r.get("reasons") or [])}
        for r in reasons
    ]
    report_rows = [
        {
            "run_id": r.get("run_id"),
            "action": r.get("action"),
            "passed": r.get("passed"),
            "rows_scanned": r.get("rows_scanned"),
            "rows_failed": r.get("rows_failed"),
            "report_key": r.get("report_key"),
        }
        for r in reports
    ]

    error_block = ""
    if errors:
        items = "".join(f"<li>{_esc(item)}</li>" for item in errors)
        error_block = f"<section class='errors'><h2>Warnings</h2><ul>{items}</ul></section>"

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\"/>
  <title>Lakehouse quality dashboard</title>
  <style>
    :root {{ font-family: ui-sans-serif, system-ui, sans-serif; color: #12202a; }}
    body {{ margin: 2rem auto; max-width: 960px; line-height: 1.45; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .meta {{ color: #4a5b66; font-size: 0.9rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 0.6rem 0 1.4rem; }}
    th, td {{ border: 1px solid #d5dee4; padding: 0.4rem 0.55rem; text-align: left; }}
    th {{ background: #eef3f6; }}
    .empty {{ color: #6a7b86; }}
    .errors {{ background: #fff4e5; padding: 0.6rem 1rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, monospace; }}
  </style>
</head>
<body>
  <h1>Medallion quality dashboard</h1>
  <p class=\"meta\">
    Generated {_esc(data.get('generated_at'))} · backend={_esc(data.get('backend'))} ·
    Silver bucket <code>{_esc(data.get('silver_bucket'))}</code>
  </p>
  {error_block}
  <section>
    <h2>Spec gate (fixture batch)</h2>
    <p class=\"meta\">
      action={_esc(spec.get('action'))} · passed={_esc(spec.get('passed'))} ·
      scanned={_esc(spec.get('rows_scanned'))} · failed={_esc(spec.get('rows_failed'))} ·
      fail_ratio={_esc(spec.get('fail_ratio'))}
    </p>
    {_rows_table(check_rows, ['check_name', 'passed', 'rows_scanned', 'rows_failed'])}
  </section>
  <section>
    <h2>Failing fixture rows</h2>
    {_rows_table(reason_rows, ['event_id', 'reasons'])}
  </section>
  <section>
    <h2>Live quality reports</h2>
    {_rows_table(report_rows, ['run_id', 'action', 'passed', 'rows_scanned', 'rows_failed', 'report_key'])}
  </section>
  <section>
    <h2>Recent pipeline runs</h2>
    {_rows_table(runs, ['run_id', 'status', 'started_at', 'error'])}
  </section>
</body>
</html>
"""


def write_html(path: Path | str, *, snapshot: dict[str, Any] | None = None) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_html(snapshot), encoding="utf-8")
    return dest


def describe_dashboard(
    *, settings: Settings | None = None, out: str | None = None
) -> dict[str, Any]:
    snapshot = collect_snapshot(settings=settings)
    spec = dict(snapshot.get("spec") or {})
    result: dict[str, Any] = {
        "ok": True,
        "backend": snapshot.get("backend"),
        "action": spec.get("action"),
        "rows_scanned": spec.get("rows_scanned"),
        "rows_failed": spec.get("rows_failed"),
        "check_names": snapshot.get("check_names") or [],
        "report_count": len(snapshot.get("reports") or []),
        "run_count": len(snapshot.get("runs") or []),
        "html_path": None,
        "errors": snapshot.get("errors") or [],
    }
    if out:
        result["html_path"] = str(write_html(out, snapshot=snapshot))
    return result
