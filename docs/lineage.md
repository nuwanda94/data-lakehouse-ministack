# Dataset lineage

Post-v1.0 increment: a first-class **lineage snapshot** that does not
depend on OpenLineage, Marquez, or a live MiniStack session.

## What it shows

* Zone nodes: Bronze raw events, Silver cleansed events, Silver quality
  reports, Gold daily metrics, Gold quarantine rejected metrics,
  DynamoDB pipeline-run rows
* Edges: `cleanse`, `gate`, `aggregate`, `reject` (quality → Gold
  quarantine), `unreadable` (Silver → Gold quarantine), `run_metadata`
* Live object counts when MiniStack answers
* A Mermaid flowchart you can paste into GitHub or the README

Gold splits after the quality gate: contract-valid aggregates follow
`quality -->|aggregate| gold`; rejected metrics and unreadable Silver
contributions follow the side path into `gold_quarantine/`
(`quality -->|reject| gold_quarantine`,
`silver -->|unreadable| gold_quarantine`). Both leaves emit
`run_metadata` to DynamoDB.

When S3 or DynamoDB is unreachable the graph still renders from the
hermetic spec (`backend=spec`).

## Commands

```bash
python -m lakehouse lineage
python -m lakehouse lineage --out build/lineage.mmd
make lineage
```

The JSON printed by the CLI is what CI asserts on. Open the `.mmd` file
in any Mermaid previewer.
