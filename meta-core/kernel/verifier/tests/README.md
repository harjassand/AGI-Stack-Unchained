# Verifier Test Fixtures

## Golden receipt generation

Run this command from `meta-core/kernel/verifier` to regenerate
`tests/golden/valid_receipt.json` deterministically:

```bash
RUSTUP_TOOLCHAIN=1.76.0 cargo run --bin verifier -- \
  verify \
  --bundle-dir tests/fixtures/valid_bundle \
  --parent-bundle-dir tests/fixtures/parent_bundle \
  --meta-dir ../../meta_constitution/v1 \
  --out tests/golden/valid_receipt.json
```
