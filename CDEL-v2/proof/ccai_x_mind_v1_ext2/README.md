# CCAI-X Mind v1 Extension-2 Proof Pack

This proof pack is additive to the existing Mind v1 proof pack. It exercises RSI success, ablation battery, and witness-bearing suites without modifying the original proof pack or fixtures.

## One-command entrypoint

From repo root:

```
./prove_ccai_x_mind_v1_rsi_success.sh /tmp/ccai_x_mind_v1_ext2_proof 1
```

## Outputs

- `rsi_success_manifest.json` (GCJ-1 canonical)
- `ablation_matrix.json` (GCJ-1 canonical)
- `rsi/` run directory with deterministic learning_state and receipts
- `runs/pass_dev`, `runs/pass_heldout` baseline PASS receipts
- `ablations/` FAIL fixtures (no receipts)
- `baseline_mind_v1/` baseline proof pack run + receipt hashes

## Verify without rerun

```
python3 CDEL-v2/proof/ccai_x_mind_v1_ext2/verify_out_dir_ext2_v1.py /tmp/ccai_x_mind_v1_ext2_proof
```
