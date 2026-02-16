# v10.0 Sovereign Model Genesis Protocol Contract (SMG Protocol v1)

## Scope
This contract governs the v10.0 model genesis pipeline. All requirements are normative and fail-closed.

## SMG-CONST-OFFLINE-0
Training/eval must be offline; any network_used=true is fatal.

## SMG-CONST-KEYS-0
Training requires ENABLE_RESEARCH + ENABLE_MODEL_GENESIS + ENABLE_TRAINING + valid lease.

## SMG-CONST-PROVENANCE-0
Corpus may include only VALID v8/v9 receipts and TRAIN/DEV splits.

## SMG-CONST-NO-HELDOUT-LEAK-0
Heldout suite IDs must not appear in corpus indexes or training data.

## SMG-CONST-PIN-0
Toolchain/config/corpus hashes are pinned and must match sealed receipts.

## SMG-CONST-EVAL-0
Promotion requires heldout eval receipts meeting thresholds and no safety regression.

## SMG-CONST-ACTIVATE-0
Activation is two-phase and rollbackable.
