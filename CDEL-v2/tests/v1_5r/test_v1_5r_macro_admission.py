from cdel.v1_5r.ctime.macro import admit_macro, compute_macro_id, compute_rent_bits
from cdel.v1_5r.ctime.trace import build_trace_event


def _make_trace_events() -> list[dict]:
    events = []
    for idx in range(12):
        name = "A" if idx % 2 == 0 else "B"
        events.append(
            build_trace_event(
                epoch_id="epoch",
                t_step=idx,
                family_id="sha256:" + "0" * 64,
                inst_hash="sha256:" + "1" * 64,
                action_name=name,
                action_args={},
                macro_id=None,
                obs_hash="sha256:" + "2" * 64,
                post_obs_hash="sha256:" + "3" * 64,
                receipt_hash="sha256:" + "4" * 64,
                duration_steps=1,
            )
        )
    return events


def test_macro_admission_passes_min_support() -> None:
    trace_events = _make_trace_events()
    macro = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "body": [{"name": "A", "args": {}}, {"name": "B", "args": {}}],
        "guard": None,
        "admission_epoch": 0,
    }
    macro["rent_bits"] = compute_rent_bits(macro)
    macro["macro_id"] = compute_macro_id(macro)

    report = admit_macro(macro, trace_events, f_min=1, n_min=2, delta_min_bits=-10_000)
    assert report["decision"] == "PASS"
    assert report["support_total_hold"] >= 2


def test_macro_admission_rejects_bad_id() -> None:
    trace_events = _make_trace_events()
    macro = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "body": [{"name": "A", "args": {}}, {"name": "B", "args": {}}],
        "guard": None,
        "admission_epoch": 0,
        "rent_bits": 0,
        "macro_id": "sha256:" + "5" * 64,
    }
    report = admit_macro(macro, trace_events, f_min=1, n_min=2, delta_min_bits=0)
    assert report["decision"] == "FAIL"
    assert "macro_id_mismatch" in report["errors"]
