# Data quality dashboard

Phase 4 leftover: a first-class **quality summary** that does not depend on
Streamlit or a live MiniStack session.

## What it shows

* Named gate checks (`event_id_present`, `known_event_type`,
  `required_dimensions`, `quantity_and_amount_sane`, `schema_valid`)
* Fixture-batch pass / fail / quarantine decision and fail ratio
* Live Silver `quality/dt=…/run_id=….json` reports when MiniStack is up
* Recent DynamoDB pipeline-run rows

When S3 or DynamoDB is unreachable the page still renders from the
hermetic fixture batch (`backend=spec`).

## Commands

```bash
python -m lakehouse quality-dashboard
python -m lakehouse quality-dashboard --out build/quality-dashboard.html
make quality-dashboard
```

The JSON printed by the CLI is what CI asserts on. Open the HTML file in a
browser; there is no extra web framework in the core install.
