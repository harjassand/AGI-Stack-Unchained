from cdel.gen.proof_synth import synthesize_missing_proofs
from cdel.kernel.parse import parse_definition


def test_proof_synth_by_eval():
    defn_json = {
        "name": "const_two",
        "params": [],
        "ret_type": {"tag": "int"},
        "body": {"tag": "int", "value": 2},
        "termination": {"kind": "structural", "decreases_param": None},
    }
    defn = parse_definition(defn_json)
    defs = {defn.name: defn}
    specs = [
        {
            "kind": "proof_unbounded",
            "goal": {
                "tag": "eq",
                "lhs": {"tag": "app", "fn": {"tag": "sym", "name": "const_two"}, "args": []},
                "rhs": {"tag": "int", "value": 2},
            },
            "proof": {"tag": "missing"},
        }
    ]
    new_specs, count = synthesize_missing_proofs(specs, defs, step_limit=100)
    assert count == 1
    assert new_specs[0]["proof"]["tag"] == "by_eval"
