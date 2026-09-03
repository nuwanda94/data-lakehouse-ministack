# Progress Log — hourly-chore-feat automation

This file is updated by the `hourly-chore-feat` automation on every run.

## Format

```
## YYYY-MM-DD HH:MM TZ
- Completed: <type>: <title>
- Next candidate: <type>: <title> (P0/P1)
- Notes: ...
```

## Runs

## 2026-09-04 00:05 IST
- Completed: feat: Lineage path-ratio alert on Bronze-split cleanse floor
- Next candidate: feat: Lineage path-ratio alert on quality-split aggregate floor
- Notes: Bronze-split cleanse share is compared to `LAKEHOUSE_LINEAGE_BRONZE_CLEANSE_FLOOR` (default 0.80) or `--bronze-cleanse-floor`. Spec fixtures stay green at 0.8571. Either family or Bronze cut flips `path_ratio_alert.ok`. CLI JSON `cuts.bronze_split`; Mermaid records `%% bronze-split alert: …`. `python -m lakehouse lineage` exits 1 on a Bronze-split breach. Docs in `docs/lineage.md`.

## 2026-09-03 23:16 IST
- Completed: feat: Lineage path-ratio alert threshold (cleanse share floor)
- Next candidate: feat: Lineage path-ratio alert on Bronze-split cleanse floor
- Notes: Family cleanse share is compared to `LAKEHOUSE_LINEAGE_CLEANSE_FLOOR` (default 0.60) or `--cleanse-floor`. Spec fixtures stay green at 0.6667. CLI JSON exposes `path_ratio_alert`; Mermaid records `%% path-ratio alert: …`. `python -m lakehouse lineage` exits 1 on a breach. Docs in `docs/lineage.md`.

## 2026-09-03 22:30 IST
- Completed: feat: Lineage path ratios (cleanse vs reject vs quarantine)
- Next candidate: feat: Lineage path-ratio alert threshold (cleanse share floor)
- Notes: Spec + live graphs fold destination edge weights into family ratios (`cleanse` = cleanse/gate/aggregate, `reject` = reject/unreadable, `quarantine`). Named cuts: `bronze_split` and `quality_split`. CLI JSON exposes `path_ratios`; Mermaid records `%% path ratios: …`. Docs in `docs/lineage.md`.
