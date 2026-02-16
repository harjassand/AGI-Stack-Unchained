# Conformance Harness v1

This directory defines a black-box conformance harness for CDEL Evaluate implementations.

## Supported Modes

The runner can target one of three interface styles:

- HTTP: POST JSON to an Evaluate endpoint.
- Subprocess: run a local binary that reads request JSON on stdin and writes response JSON to stdout.
- File IPC: write request JSON to a requests directory and wait for a response JSON in a responses directory.

## Usage

HTTP:

```bash
python3 conformance/run.py \
  --mode http \
  --http-url http://localhost:8080/evaluate/v1
```

Subprocess:

```bash
python3 conformance/run.py \
  --mode subprocess \
  --subprocess-cmd "./bin/cdel_evaluate"
```

File IPC:

```bash
python3 conformance/run.py \
  --mode file \
  --ipc-dir /tmp/cdel_ipc
```

File IPC conventions:

- The runner writes `requests/<id>.json` under `--ipc-dir`.
- The implementation MUST write `responses/<id>.json` with the response body.
- The runner waits up to the configured timeout for the response file.

## Test Catalog

The harness loads `conformance/tests/catalog.json`. Tests include:

- Invalid capsule schema => FAIL.
- Receipt binding checks on PASS.
- Ledger invariant checks (spec-level simulations).
- Response shape checks (PASS/FAIL only; receipt only on PASS).

Some tests require a PASS outcome and may need a test fixture in the target implementation.

## Mock Endpoint Smoke Test

Use the mock endpoint for an end-to-end harness check:

```bash
./conformance/run_against_mock.sh
```

This uses `conformance/tests/mock_catalog.json` with a known PASS capsule.

## Dependencies

Standard library only.
