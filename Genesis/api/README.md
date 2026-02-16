# Evaluate API v1

This directory defines the normative wire protocol for the CDEL Evaluate boundary.

## Files

- `evaluate_v1.openapi.yaml`: OpenAPI 3.0 spec for Evaluate v1.

## Stability and Versioning

- The Evaluate v1 protocol is immutable once released.
- Backward-incompatible changes MUST use a new file (e.g., `evaluate_v2.openapi.yaml`).
- Implementations MUST enforce the binary-only response rule (PASS/FAIL only; receipt only on PASS).

## Stub Generation (examples)

Use any OpenAPI 3 generator. These commands are illustrative; choose a target language as needed.

```bash
openapi-generator-cli generate \
  -i api/evaluate_v1.openapi.yaml \
  -g <language> \
  -o build/evaluate_v1_stub
```

## Normative References

- Capsule schema: `schema/capsule.schema.json`
- Receipt schema: `schema/receipt.schema.json`
- Evaluate protocol spec: `docs/evaluate_protocol.md`
