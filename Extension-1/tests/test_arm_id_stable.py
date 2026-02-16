from pathlib import Path
import json

from self_improve_code_v1.targets.load_arms_v1 import load_arms, compute_arm_id


def test_arm_id_stable():
    raw = json.loads(Path("/Users/harjas/AGI Stack/Extension-1/self_improve_code_v1/targets/arms_v1.json").read_text())
    arms_raw = raw.get("arms", raw)
    for arm in arms_raw:
        assert arm["arm_id"] == compute_arm_id(arm)
    arms = load_arms("/Users/harjas/AGI Stack/Extension-1/self_improve_code_v1/targets/arms_v1.json")
    assert len(arms) == len(arms_raw)
