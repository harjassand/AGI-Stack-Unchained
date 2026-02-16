# pyut-harness-v1 sandbox runbook

This document describes the sandbox guarantees and failure modes for
`pyut-harness-v1`.

## Guarantees (best-effort, fail-closed)

- Executes each test case in a fresh temp directory with no repo paths.
- Scrubs the child environment to a minimal allowlist.
- Uses isolated Python flags: `-I -S -E -B`.
- Blocks imports and disallows access to dunder attributes.
- Restricts builtins to a small safe subset.
- Applies resource limits when supported by the platform.
- Enforces a hard timeout per test case.
- Captures stdout/stderr with size limits and truncation.

## Limits (current defaults)

- Timeout: 0.2s per test case
- CPU time: 1s (RLIMIT_CPU)
- Address space: 256MB (RLIMIT_AS)
- File size: 1MB (RLIMIT_FSIZE)
- File descriptors: 32 (RLIMIT_NOFILE)
- Processes: 16 (RLIMIT_NPROC)
- Stdout cap: 4096 bytes
- Stderr cap: 4096 bytes

If `resource` is unavailable, only timeouts are enforced and the
artifact will report `limits_applied = false`.

## Error categories (artifacts)

Artifacts normalize failures into a small set of categories:

- `timeout` (timeout or SIGXCPU)
- `mem_limit` (MemoryError/SIGKILL)
- `security_violation` (import/dunder/banned name)
- `syntax_error` (SyntaxError)
- `runtime_error` (everything else, including mismatches)

## Local reproduction

To reproduce a failure locally:

1) Run the pyut smoke script:

```
./scripts/smoke_pyut_harness_adopt.sh
```

2) If you want to isolate a single test case, use the harness runner
logic in `cdel/sealed/harnesses/pyut_v1.py` and provide:

- `source` (function source string)
- `fn_name`
- `args`
- `expected`

## Notes

- The harness is deterministic as long as suite bytes and inputs are
  fixed.
- No network access is permitted.
- Any unexpected errors fail the candidate (fail-closed).
