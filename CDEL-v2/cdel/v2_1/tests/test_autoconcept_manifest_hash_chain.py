from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_1.autoconcept import write_autoconcept_outputs
from cdel.v2_1.verify_rsi_demon_v7 import _validate_manifest


def test_autoconcept_manifest_hash_chain() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "attempt"
        outputs = write_autoconcept_outputs(
            run_dir=run_dir,
            run_id="sha256:" + "2" * 64,
            attempt_id="attempt_0001",
            insertion_index=0,
            candidate_rank=0,
            active_concept_patches=[],
        )
        manifest = dict(outputs["manifest"])
        manifest["candidate_rank"] = int(manifest["candidate_rank"]) + 1
        with pytest.raises(CanonError) as exc:
            _validate_manifest(manifest)
        assert str(exc.value) == "CANON_HASH_MISMATCH"
