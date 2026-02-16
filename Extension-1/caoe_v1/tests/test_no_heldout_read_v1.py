import json
import os
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from cli.caoe_proposer_cli_v1 import main  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle)


def _write_stub_cdel(path: Path) -> None:
    code = """#!/usr/bin/env python3
import json
import sys
import tarfile
from pathlib import Path

args = sys.argv[1:]
if len(args) < 2 or args[0] != 'caoe' or args[1] != 'verify':
    sys.exit(2)

def _get(flag):
    if flag not in args:
        return None
    idx = args.index(flag)
    return args[idx + 1]

candidate = _get('--candidate')
out_dir = _get('--out')
progress_path = _get('--progress_path')
if candidate is None or out_dir is None:
    sys.exit(2)

with tarfile.open(candidate, 'r') as tf:
    manifest = json.load(tf.extractfile('manifest.json'))
    patch = json.load(tf.extractfile('ontology_patch.json'))

if progress_path:
    Path(progress_path).write_text(json.dumps({
        'format': 'caoe_progress_v1_1',
        'schema_version': 1,
        'phase': 'dev_base',
        'episodes_done': 0,
        'episodes_total': 1,
        'candidate_id': manifest.get('candidate_id', ''),
        'eval_plan': 'screen',
        'stable_time': 0,
    }))

candidate_id = manifest.get('candidate_id')
ops = patch.get('ops') or []

is_identity = len(ops) == 0

if is_identity:
    report = {
        'format': 'evidence_report_v1_1',
        'schema_version': 1,
        'candidate_id': candidate_id,
        'decision': 'PASS',
        'failed_contract': 'NONE',
        'base_metrics': {
            'c_inv': {
                'per_regime_success': {'r1': 0.2, 'r2': 0.3},
                'per_regime_efficiency': {'r1': 0.4, 'r2': 0.5},
                'heldout_worst_case_success': 0.2,
                'heldout_worst_case_efficiency': 0.4,
                'per_family': {
                    'fam': {
                        'avg_success': 0.25,
                        'avg_efficiency': 0.45,
                        'worst_case_success': 0.2,
                        'worst_case_efficiency': 0.4,
                        'regimes_evaluated': ['r1', 'r2'],
                    }
                },
                'evaluated_families': ['fam'],
                'evaluated_regimes': ['r1', 'r2'],
            },
            'c_mdl': {
                'dev_tml_bits': 90,
                'heldout_tml_bits': 100,
                'dev_tml_bits_base': 90,
                'dev_tml_bits_candidate': 90,
                'heldout_tml_bits_base': 100,
                'heldout_tml_bits_candidate': 100,
                'delta_min_bits': 256,
                'pass_reason': '',
                'failure_reason': '',
            },
            'c_anti': {'leakage_sensitivity': 0.1, 'relabel_sensitivity': 0.1},
            'ccai_x': {'per_regime': {}},
            'diagnostics': {'phi_fingerprint': '0' * 64, 'policy_fingerprint': '0' * 64},
        },
        'candidate_metrics': {
            'c_inv': {
                'per_regime_success': {'r1': 0.2, 'r2': 0.3},
                'per_regime_efficiency': {'r1': 0.4, 'r2': 0.5},
                'heldout_worst_case_success': 0.2,
                'heldout_worst_case_efficiency': 0.4,
                'per_family': {
                    'fam': {
                        'avg_success': 0.25,
                        'avg_efficiency': 0.45,
                        'worst_case_success': 0.2,
                        'worst_case_efficiency': 0.4,
                        'regimes_evaluated': ['r1', 'r2'],
                    }
                },
                'evaluated_families': ['fam'],
                'evaluated_regimes': ['r1', 'r2'],
            },
            'c_mdl': {
                'dev_tml_bits': 90,
                'heldout_tml_bits': 100,
                'dev_tml_bits_base': 90,
                'dev_tml_bits_candidate': 90,
                'heldout_tml_bits_base': 100,
                'heldout_tml_bits_candidate': 100,
                'delta_min_bits': 256,
                'pass_reason': '',
                'failure_reason': '',
            },
            'c_anti': {'leakage_sensitivity': 0.1, 'relabel_sensitivity': 0.1},
            'ccai_x': {'per_regime': {}},
            'diagnostics': {'phi_fingerprint': '0' * 64, 'policy_fingerprint': '0' * 64},
        },
        'contracts': {'C-ANTI': {'pass': True}, 'C-DO': {'pass': True}, 'C-MDL': {'pass': True}, 'C-INV': {'pass': True}, 'C-LIFE': {'pass': True}},
    }
else:
    gain = patch.get('predicted_gains', {}).get('delta_worst_case_success', 0)
    decision = 'PASS' if gain > 0.1 else 'FAIL'
    report = {
        'format': 'evidence_report_v1_1',
        'schema_version': 1,
        'candidate_id': candidate_id,
        'decision': decision,
        'failed_contract': 'NONE' if decision == 'PASS' else 'C-INV',
        'base_metrics': {
            'c_inv': {
                'per_regime_success': {'r1': 0.2, 'r2': 0.3},
                'per_regime_efficiency': {'r1': 0.4, 'r2': 0.5},
                'heldout_worst_case_success': 0.2,
                'heldout_worst_case_efficiency': 0.4,
                'per_family': {
                    'fam': {
                        'avg_success': 0.25,
                        'avg_efficiency': 0.45,
                        'worst_case_success': 0.2,
                        'worst_case_efficiency': 0.4,
                        'regimes_evaluated': ['r1', 'r2'],
                    }
                },
                'evaluated_families': ['fam'],
                'evaluated_regimes': ['r1', 'r2'],
            },
            'c_mdl': {
                'dev_tml_bits': 90,
                'heldout_tml_bits': 100,
                'dev_tml_bits_base': 90,
                'dev_tml_bits_candidate': 90,
                'heldout_tml_bits_base': 100,
                'heldout_tml_bits_candidate': 100,
                'delta_min_bits': 256,
                'pass_reason': '',
                'failure_reason': '',
            },
            'c_anti': {'leakage_sensitivity': 0.1, 'relabel_sensitivity': 0.1},
            'ccai_x': {'per_regime': {}},
            'diagnostics': {'phi_fingerprint': '0' * 64, 'policy_fingerprint': '0' * 64},
        },
        'candidate_metrics': {
            'c_inv': {
                'per_regime_success': {'r1': 0.2, 'r2': 0.3},
                'per_regime_efficiency': {'r1': 0.4, 'r2': 0.5},
                'heldout_worst_case_success': 0.3,
                'heldout_worst_case_efficiency': 0.5,
                'per_family': {
                    'fam': {
                        'avg_success': 0.25,
                        'avg_efficiency': 0.45,
                        'worst_case_success': 0.2,
                        'worst_case_efficiency': 0.4,
                        'regimes_evaluated': ['r1', 'r2'],
                    }
                },
                'evaluated_families': ['fam'],
                'evaluated_regimes': ['r1', 'r2'],
            },
            'c_mdl': {
                'dev_tml_bits': 90,
                'heldout_tml_bits': 90,
                'dev_tml_bits_base': 90,
                'dev_tml_bits_candidate': 90,
                'heldout_tml_bits_base': 100,
                'heldout_tml_bits_candidate': 90,
                'delta_min_bits': 256,
                'pass_reason': '',
                'failure_reason': '',
            },
            'c_anti': {'leakage_sensitivity': 0.1, 'relabel_sensitivity': 0.1},
            'ccai_x': {'per_regime': {}},
            'diagnostics': {'phi_fingerprint': '0' * 64, 'policy_fingerprint': '0' * 64},
        },
        'contracts': {'C-ANTI': {'pass': True}, 'C-DO': {'pass': True}, 'C-MDL': {'pass': True}, 'C-INV': {'pass': decision == 'PASS'}, 'C-LIFE': {'pass': True}},
    }

out_path = Path(out_dir)
out_path.mkdir(parents=True, exist_ok=True)
with (out_path / 'evidence_report.json').open('w', encoding='utf-8') as f:
    json.dump(report, f)
with (out_path / 'receipt.json').open('w', encoding='utf-8') as f:
    json.dump({'candidate_id': candidate_id, 'decision': report['decision']}, f)
"""
    path.write_text(code)
    path.chmod(0o755)


def test_no_heldout_read_v1(monkeypatch, tmp_path: Path):
    base_ontology = {
        "format": "ontology_spec_v1_1",
        "schema_version": 1,
        "ontology_hash": "0" * 64,
        "isa_version": "caoe_absop_isa_v1_2",
        "symbols": [],
        "measurement_phi": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [],
            "outputs": [{"name": "y", "type": "bit"}],
            "ops": [],
            "max_ops": 1,
        },
        "lowering_lambda": {
            "format": "bounded_program_v1",
            "schema_version": 1,
            "inputs": [],
            "outputs": [{"name": "x", "type": "bit"}],
            "ops": [],
            "max_ops": 1,
        },
        "supports_macro_do": False,
        "supports_repeat_action_options": False,
        "lifting_psi": None,
        "complexity_limits": {
            "phi_max_ops": 1,
            "lambda_max_ops": 1,
            "psi_max_ops": 1,
            "max_constants": 4,
            "max_state_history": 1,
        },
    }
    base_mech = {"format": "mechanism_registry_v1_1", "schema_version": 1, "mechanisms": []}
    suitepack_dev = {"suitepack_id": "dev_suite"}

    base_ontology_path = tmp_path / "base_ontology.json"
    base_mech_path = tmp_path / "base_mech.json"
    suitepack_dev_path = tmp_path / "suitepack_dev.json"
    suitepack_heldout_path = tmp_path / "heldout_suite.json"

    _write_json(base_ontology_path, base_ontology)
    _write_json(base_mech_path, base_mech)
    _write_json(suitepack_dev_path, suitepack_dev)
    suitepack_heldout_path.write_text("heldout")

    cdel_bin = tmp_path / "cdel_stub.py"
    _write_stub_cdel(cdel_bin)

    original_open = open

    def guarded_open(path, *args, **kwargs):
        if str(path) == str(suitepack_heldout_path):
            raise RuntimeError("heldout path read")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", guarded_open)

    out_dir = tmp_path / "out"
    state_dir = tmp_path / "state"

    argv = [
        "run-epoch",
        "--epoch_id",
        "e1",
        "--base_ontology",
        str(base_ontology_path),
        "--base_mech",
        str(base_mech_path),
        "--suitepack_dev",
        str(suitepack_dev_path),
        "--suitepack_heldout",
        str(suitepack_heldout_path),
        "--heldout_suite_id",
        "heldout_suite",
        "--cdel_bin",
        str(cdel_bin),
        "--state_dir",
        str(state_dir),
        "--out_dir",
        str(out_dir),
        "--max_candidates",
        "2",
    ]

    main(argv)
