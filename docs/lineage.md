# Dataset lineage

Post-v1.0 increment: a first-class **lineage snapshot** that does not
depend on OpenLineage, Marquez, or a live MiniStack session.

## What it shows

* Zone nodes: Bronze raw events, Silver cleansed events, Silver quality
  reports, Gold daily metrics, DynamoDB pipeline-run rows
* Edges: `cleanse`, `gate`, `aggregate`, `run_metadata`
* Live object counts when MiniStack answers
* A Mermaid flowchart you can paste into GitHub or the README

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
