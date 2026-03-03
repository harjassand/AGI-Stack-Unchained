# Orchestrator Active Inference Inputs v1

Runtime input queue for active inference query generation.

## Layout

- `query_inputs/`: Tick-scoped JSONL files with `active_inference_query_v1` records.

## Record Shape

Each JSONL line is a canonical query object:

- `schema_version`: Expected to be `active_inference_query_v1`.
- `query`: Prompt/query text consumed by active inference routines.

## Notes

- Files are append-only per tick in normal operation.
- Keep line-delimited JSON formatting; downstream consumers read one record per line.
