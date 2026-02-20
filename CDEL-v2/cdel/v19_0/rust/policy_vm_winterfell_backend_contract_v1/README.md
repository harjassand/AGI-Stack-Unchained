# policy_vm_winterfell_backend_contract_v1

Emits the pinned `policy_vm_winterfell_backend_contract_v1` artifact for Phase 4 contract freeze.

## Usage

```bash
cargo run --release -- --emit-contract /path/to/policy_vm_winterfell_backend_contract_v1.json
```

If `--emit-contract` is omitted, the JSON payload is printed to stdout.

## Contract pins

- `winterfell = "=0.13.1"` (exact semver pin)
- Field ID: `WINTERFELL_F128`
- Extension ID: `FIELD_EXTENSION_NONE_DEGREE_1`
- Merkle hasher ID: `winterfell::crypto::hashers::Blake3_256`
- Random coin hasher ID: `winterfell::crypto::DefaultRandomCoin<Blake3_256>`
