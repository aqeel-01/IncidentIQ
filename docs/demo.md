# IncidentIQ end-to-end demo

Reproducible local demonstration of the full investigation pipeline.

## Scenario

**payments-api deployment regression**

| Signal | Detail |
| ------ | ------ |
| Deployment | `v1.2.2` / `deploy123` at T−60m |
| Metrics | `error_rate` 0.12 → 0.9, `db_connection_errors` |
| Logs | database connection timeouts + checkout failures |
| Alert | `HighErrorRate` firing at T+5m |

## Run

```bash
python -m app.domain.demo
```

Options:

```bash
python -m app.domain.demo \
  --work-dir data/demo \
  --output data/demo/result.json
```

Uses an on-disk SQLite DB under `--work-dir` by default (no Postgres/Redis/Ollama
required). Pass `--database-url` to use another database.

## Pipeline covered

`collect_sources` → `parse` → `normalize` → `deduplicate` → `group_errors` →
`detect_anomalies` → `build_timeline` → `correlate` → `build_evidence` →
`calculate_evidence_quality` → `build_rca_package` → `run_rca` → `persist_rca`

AI stages use a deterministic fake provider so results are stable across runs.

## Expected output fields

- Root cause + confidence
- Supporting evidence
- Contradicting evidence
- Alternative hypotheses
- Verification steps
- Evidence quality
