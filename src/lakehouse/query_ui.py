"""Simple analyst query UI for Gold + pipeline runs.

MiniStack rarely emulates Athena and we do not pull Streamlit into the
core install. This module:

* gathers Gold DynamoDB metrics and pipeline-run rows when AWS is up
* always includes the named Athena SQL from ``lakehouse.athena``
* renders a self-contained HTML dashboard
* ships a notebook that reuses the same snapshot helper

``python -m lakehouse ui --out build/query-ui.html`` writes the page.
``--serve`` starts a stdlib HTTP server (opt-in; not used in CI).
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lakehouse.athena import named_queries
from lakehouse.config import Settings, load_settings

NOTEBOOK_RELPATH = "notebooks/gold_query.ipynb"


def notebook_path() -> Path:
    return Path(__file__).resolve().parents[2] / NOTEBOOK_RELPATH


def collect_snapshot(*, settings: Settings | None = None) -> dict[str, Any]:
    """Build a JSON-serializable snapshot for the UI / notebook."""

    errors: list[str] = []
    resolved = settings
    if resolved is None:
        try:
            resolved = load_settings()
        except Exception as exc:
            errors.append(f"settings: {exc}")
            resolved = None
    snapshot: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "gold_bucket": getattr(resolved, "gold_bucket", "lakehouse-local-gold"),
        "gold_metrics_table": getattr(
            resolved, "gold_metrics_table", "lakehouse-local-gold-metrics"
        ),
        "pipeline_runs_table": getattr(
            resolved, "pipeline_runs_table", "lakehouse-local-pipeline-runs"
        ),
        "gold_objects": [],
        "metrics": [],
        "runs": [],
        "named_queries": [q.as_dict() for q in named_queries()],
        "errors": list(errors),
        "backend": "spec" if resolved is None else "live",
    }
    if resolved is None:
        return snapshot
    try:
        from lakehouse.ops.query import query_gold

        gold = query_gold(settings=resolved)
        snapshot["gold_objects"] = list(gold.get("gold_objects") or [])
        snapshot["metrics"] = list(gold.get("metrics") or [])
    except Exception as exc:  # MiniStack / tables may be absent in unit CI
        snapshot["backend"] = "spec"
        snapshot["errors"].append(f"gold: {exc}")
    try:
        from lakehouse.ops.runs import query_runs

        runs = query_runs(settings=resolved, limit=15)
        snapshot["runs"] = list(runs.get("runs") or [])
    except Exception as exc:
        snapshot["backend"] = "spec"
        snapshot["errors"].append(f"runs: {exc}")
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
    metrics = list(data.get("metrics") or [])
    runs = list(data.get("runs") or [])
    objects = list(data.get("gold_objects") or [])
    queries = list(data.get("named_queries") or [])
    errors = list(data.get("errors") or [])

    query_blocks: list[str] = []
    for query in queries:
        query_blocks.append(
            "<article class='query'>"
            f"<h3>{_esc(query.get('name'))}</h3>"
            f"<p>{_esc(query.get('description'))}</p>"
            f"<pre><code>{_esc(query.get('sql'))}</code></pre>"
            "</article>"
        )

    object_items = "".join(f"<li><code>{_esc(key)}</code></li>" for key in objects) or (
        "<li class='empty'>No Gold objects yet — run <code>make pipeline</code>.</li>"
    )
    error_block = ""
    if errors:
        items = "".join(f"<li>{_esc(item)}</li>" for item in errors)
        error_block = f"<section class='errors'><h2>Warnings</h2><ul>{items}</ul></section>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Lakehouse query UI</title>
  <style>
    :root {{ font-family: ui-sans-serif, system-ui, sans-serif; color: #12202a; }}
    body {{ margin: 2rem auto; max-width: 960px; line-height: 1.45; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .meta {{ color: #4a5b66; font-size: 0.9rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 0.6rem 0 1.4rem; }}
    th, td {{ border: 1px solid #d5dee4; padding: 0.4rem 0.55rem; text-align: left; }}
    th {{ background: #eef3f6; }}
    pre {{ background: #0f1c24; color: #e8f0f4; padding: 0.8rem; overflow-x: auto; }}
    .empty {{ color: #6a7b86; }}
    .errors {{ background: #fff4e5; padding: 0.6rem 1rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, monospace; }}
  </style>
</head>
<body>
  <h1>Medallion query UI</h1>
  <p class="meta">
    Generated {_esc(data.get('generated_at'))} · backend={_esc(data.get('backend'))} ·
    Gold bucket <code>{_esc(data.get('gold_bucket'))}</code>
  </p>
  {error_block}
  <section>
    <h2>Gold metrics (DynamoDB)</h2>
    {_rows_table(metrics, ['metric_day', 'event_type', 'dt', 'events', 'amount_usd'])}
  </section>
  <section>
    <h2>Gold objects</h2>
    <ul>{object_items}</ul>
  </section>
  <section>
    <h2>Recent pipeline runs</h2>
    {_rows_table(runs, ['run_id', 'status', 'started_at', 'finished_at'])}
  </section>
  <section>
    <h2>Named Athena queries</h2>
    <p class="meta">SQL is always shown. Start one with
    <code>python -m lakehouse athena --name gold_daily_totals</code> when Athena exists.</p>
    {''.join(query_blocks)}
  </section>
</body>
</html>
"""


def write_html(path: Path | str, *, snapshot: dict[str, Any] | None = None) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_html(snapshot), encoding="utf-8")
    return dest


def describe_ui(*, settings: Settings | None = None, out: str | None = None) -> dict[str, Any]:
    snapshot = collect_snapshot(settings=settings)
    result: dict[str, Any] = {
        "ok": True,
        "backend": snapshot.get("backend"),
        "gold_object_count": len(snapshot.get("gold_objects") or []),
        "metric_count": len(snapshot.get("metrics") or []),
        "run_count": len(snapshot.get("runs") or []),
        "named_queries": [q["name"] for q in snapshot.get("named_queries") or []],
        "notebook": str(notebook_path()),
        "html_path": None,
        "errors": snapshot.get("errors") or [],
    }
    if out:
        result["html_path"] = str(write_html(out, snapshot=snapshot))
    return result


def serve_html(path: Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve the rendered file from its parent directory (blocking)."""

    import http.server
    import os
    import socketserver

    directory = str(path.parent.resolve())

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=directory, **kwargs)

    os.chdir(directory)
    with socketserver.TCPServer((host, port), Handler) as httpd:
        httpd.serve_forever()
