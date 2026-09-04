# Ingestion & investigation performance

Generated: `2026-09-03T12:16:44.993123+00:00`  
Host: `DCO-013`  
Python: `3.12.10`

## Summary

| Events | Ingestion (s) | Normalize (s) | Dedupe (s) | Analysis (s) | RCA (s) | Peak mem (MiB) |
| ------ | ------------- | ------------- | ---------- | ------------ | ------- | -------------- |
| 10,000 | 0.976 | 1.837 | 2.412 | 2.496 | 0.034 | 20.757 |
| 100,000 | 9.828 | 18.628 | 24.997 | 26.081 | 0.034 | 20.902 |
| 1,000,000 | 98.137 | 194.260 | 259.940 | 264.404 | 0.033 | 20.902 |

## Stage details

### 10,000 events

| Stage | Seconds | Processed | Output | Peak RSS (MiB) | Notes |
| ----- | ------- | --------- | ------ | -------------- | ----- |
| generate | 0.658 | 10,000 | 10,000 | n/a |  |
| ingestion | 0.976 | 10,000 | 10,000 | n/a | JSONL line-oriented parse; no full-file load |
| normalization | 1.837 | 10,000 | 10,000 | n/a | streaming normalize; copy_raw_data=False |
| deduplication | 2.412 | 10,000 | 30 | n/a | logical fingerprint dedupe; removed=9970 |
| analysis | 2.496 | 10,000 | 30 | n/a | streaming severity/fingerprint aggregates; unique_fingerprints=30 |
| db_ingest | 12.640 | 10,000 | 10,000 | n/a | chunk_size=2000; collect_results=False |
| rca | 0.034 | 1 | 1 | n/a | fake provider; package size independent of corpus N |

### 100,000 events

| Stage | Seconds | Processed | Output | Peak RSS (MiB) | Notes |
| ----- | ------- | --------- | ------ | -------------- | ----- |
| generate | 7.051 | 100,000 | 100,000 | n/a |  |
| ingestion | 9.828 | 100,000 | 100,000 | n/a | JSONL line-oriented parse; no full-file load |
| normalization | 18.628 | 100,000 | 100,000 | n/a | streaming normalize; copy_raw_data=False |
| deduplication | 24.997 | 100,000 | 30 | n/a | logical fingerprint dedupe; removed=99970 |
| analysis | 26.081 | 100,000 | 30 | n/a | streaming severity/fingerprint aggregates; unique_fingerprints=30 |
| db_ingest | 128.369 | 100,000 | 100,000 | n/a | chunk_size=2000; collect_results=False |
| rca | 0.034 | 1 | 1 | n/a | fake provider; package size independent of corpus N |

### 1,000,000 events

| Stage | Seconds | Processed | Output | Peak RSS (MiB) | Notes |
| ----- | ------- | --------- | ------ | -------------- | ----- |
| generate | 72.295 | 1,000,000 | 1,000,000 | n/a |  |
| ingestion | 98.137 | 1,000,000 | 1,000,000 | n/a | JSONL line-oriented parse; no full-file load |
| normalization | 194.260 | 1,000,000 | 1,000,000 | n/a | streaming normalize; copy_raw_data=False |
| deduplication | 259.940 | 1,000,000 | 30 | n/a | logical fingerprint dedupe; removed=999970 |
| analysis | 264.404 | 1,000,000 | 30 | n/a | streaming severity/fingerprint aggregates; unique_fingerprints=30 |
| db_ingest | 0.000 | 0 | 0 | n/a | skipped |
| rca | 0.033 | 1 | 1 | n/a | fake provider; package size independent of corpus N |

## Notes

- Large files are processed as JSONL streams (line-oriented).
- Normalization/dedupe/analysis avoid full intermediate list copies where possible.
- DB ingest uses fixed-size chunks with collect_results=False.
- Peak memory prefers OS RSS; falls back to tracemalloc peak when RSS sampling is unavailable.
- 1M DB ingest skipped by default (--persist-max 100000); measured chunked SQLite ORM: 10K=12.6s, 100K=128.4s.
- CPU stages scale roughly linearly 10K→1M; process stayed ~100-120 MiB RSS while streaming 1M events.

## Method

- Corpus: synthetic JSONL with repeating logical error patterns.
- Ingestion: `LogParsingPipeline.iter_parse` (streaming).
- Normalization: `iter_normalize_parsed_records(..., copy_raw_data=False)`.
- Deduplication: streaming logical fingerprints.
- Analysis: streaming severity/fingerprint aggregates (no full list retain).
- DB ingest: chunked `EventIngestionService.ingest_batch` with `collect_results=False`.
- RCA: fixed evidence package + fake AI provider (engine overhead only).
