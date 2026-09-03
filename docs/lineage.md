# Dataset lineage

Post-v1.0 increment: a first-class **lineage snapshot** that does not
depend on OpenLineage, Marquez, or a live MiniStack session.

## What it shows

* Zone nodes: Bronze raw events, Silver cleansed events, Silver
  quality-quarantine rows, Silver quality reports, Gold daily metrics,
  Gold quarantine rejected metrics, DynamoDB pipeline-run rows
* Combined **quarantine subgraph** grouping the Silver + Gold side
  paths (`silver_quarantine` + `gold_quarantine`) with incoming reject /
  quarantine / unreadable edges
* Edges: `cleanse`, `reject` (Bronze → Silver quarantine), `gate`,
  `quarantine` (quality → Silver quarantine), `aggregate`, `reject`
  (quality → Gold quarantine), `unreadable` (Silver → Gold quarantine),
  `run_metadata`
* Live object counts when MiniStack answers
* Edge **weights** = destination-node object counts (Silver volume on
  `cleanse`, quarantine prefix volume on `reject` / `quarantine` /
  `unreadable`, run-row count on `run_metadata`)
* Path **ratios** = family share of those weights (`cleanse` vs
  `reject` vs `quarantine`), plus Bronze and quality cuts
* A Mermaid flowchart you can paste into GitHub or the README

Silver splits after Bronze: valid events follow
`bronze -->|cleanse| silver`; poison / schema-invalid rows follow the
side path `bronze -->|reject| silver_quarantine`. The quality gate then
either promotes cleansed rows (`silver -->|gate| quality`) or writes
failing checks onto the same Silver `quarantine/` prefix
(`quality -->|quarantine| silver_quarantine`). Both leaves emit
`run_metadata` to DynamoDB.

Gold still splits after the quality gate: contract-valid aggregates
follow `quality -->|aggregate| gold`; rejected metrics and unreadable
Silver contributions follow the side path into `gold_quarantine/`
(`quality -->|reject| gold_quarantine`,
`silver -->|unreadable| gold_quarantine`).

The CLI JSON exposes `quarantine_subgraph` so dashboards can render the
side paths without walking the happy-path graph. Mermaid wraps those
nodes in `subgraph quarantine["quarantine side paths"]`.

Each edge also carries `weight` (destination object count). The CLI
prints the list as `edge_weights`. Mermaid labels look like
`bronze -->|cleanse 18| silver` so a reviewer can see volume without
opening the JSON. `quarantine_subgraph.incoming_weight` /
`outgoing_weight` sum those counts on the side-path cuts.

Path **ratios** fold those weights into three families:

* `cleanse` — `cleanse` + `gate` + `aggregate`
* `reject` — `reject` + `unreadable`
* `quarantine` — quality-gate quarantine writes

`run_metadata` edges are excluded. The CLI also exposes two named
cuts: `bronze_split` (cleanse vs reject leaving Bronze) and
`quality_split` (aggregate vs reject vs quarantine leaving quality).
Mermaid records the family mix as `%% path ratios: cleanse 0.6667
reject 0.2333 quarantine 0.1`.

A **path-ratio alert** compares the family cleanse share against a
floor (`LAKEHOUSE_LINEAGE_CLEANSE_FLOOR`, default `0.60`, or
`--cleanse-floor`). Spec fixtures sit at `0.6667`, so the default is
green. Drop the share (or raise the floor) and `python -m lakehouse
lineage` exits `1` with `path_ratio_alert.status = "breached"`.
Mermaid records `%% path-ratio alert: ok cleanse 0.6667 floor 0.6`.
The Bronze-split cleanse share is reported as a secondary cut using
the same floor; it does not flip the top-level `ok` by itself.

When S3 or DynamoDB is unreachable the graph still renders from the
hermetic spec (`backend=spec`).

## Commands

```bash
python -m lakehouse lineage
python -m lakehouse lineage --out build/lineage.mmd
python -m lakehouse lineage --cleanse-floor 0.8   # fail if cleanse share < 80%
make lineage
```

The JSON printed by the CLI is what CI asserts on. Open the `.mmd` file
in any Mermaid previewer.
