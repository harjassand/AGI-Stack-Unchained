from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v13_0.sas_science_math_v1 import q32_from_decimal_str, q32_obj_from_int

REPO_ROOT = Path(__file__).resolve().parents[4]
ORCH_ROOT = REPO_ROOT / "orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.sas_science_v13_0.controller_v1 import run_sas_science  # noqa: E402


DEFAULT_STEPS = 600
DEFAULT_DT = 0.02


@dataclass
class SASScienceState:
    run_root: Path
    state_dir: Path
    result: dict[str, Any]
    manifest_path: Path
    csv_path: Path


def _q32_obj_from_float(value: float) -> dict[str, Any]:
    q = q32_from_decimal_str(f"{value:.12f}")
    return q32_obj_from_int(int(q))


def build_manifest(
    *,
    bodies: list[str],
    dim: int = 2,
    frame_kind: str = "HELIOCENTRIC_SUN_AT_ORIGIN_V1",
    dev_fraction: float = 0.5,
    guard_steps: int = 2,
) -> dict[str, Any]:
    return {
        "manifest_version": "sas_science_dataset_manifest_v1",
        "dataset_name": "sas_science_fixture",
        "bodies": list(bodies),
        "dim": int(dim),
        "frame_kind": frame_kind,
        "units": {"time_unit": "DAY", "length_unit": "AU"},
        "timestep_policy": {
            "require_uniform_dt": True,
            "uniform_dt_tolerance_q32": _q32_obj_from_float(1e-9),
        },
        "preprocess": {"smoothing": "NONE", "derivative_method": "CENTRAL_DIFF_V1"},
        "split_policy": {
            "kind": "TIME_CONTIGUOUS_V1",
            "dev_fraction_q32": _q32_obj_from_float(dev_fraction),
            "guard_steps": int(guard_steps),
        },
        "security": {
            "forbidden_string_scan": True,
            "forbidden_strings": ["Newton", "gravity", "Gm", "1/r^2", "inverse-square"],
        },
    }


def write_dataset(
    *,
    tmp_path: Path,
    manifest: dict[str, Any],
    times: list[float],
    positions: dict[str, list[tuple[float, float]]],
) -> tuple[Path, Path]:
    bodies = list(manifest.get("bodies") or [])
    header = ["t"]
    for body in bodies:
        header.extend([f"{body}_x", f"{body}_y"])
    lines = [",".join(header)]
    for idx, t in enumerate(times):
        row = [f"{t:.10f}"]
        for body in bodies:
            x, y = positions[body][idx]
            row.append(f"{x:.10f}")
            row.append(f"{y:.10f}")
        lines.append(",".join(row))
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    manifest_path = tmp_path / "dataset_manifest.json"
    write_canon_json(manifest_path, manifest)
    return csv_path, manifest_path


def simulate_powerlaw(
    *,
    p: int,
    mu: float,
    dt: float,
    steps: int,
    x0: float,
    y0: float,
    vx0: float,
    vy0: float,
) -> list[tuple[float, float]]:
    def accel(x: float, y: float) -> tuple[float, float]:
        r = math.hypot(x, y)
        if r == 0:
            return (0.0, 0.0)
        factor = -mu / (r**p)
        return (factor * x, factor * y)

    x = x0
    y = y0
    vx = vx0
    vy = vy0
    ax, ay = accel(x, y)
    positions: list[tuple[float, float]] = []
    for _ in range(steps):
        positions.append((x, y))
        x_new = x + vx * dt + 0.5 * ax * dt * dt
        y_new = y + vy * dt + 0.5 * ay * dt * dt
        ax_new, ay_new = accel(x_new, y_new)
        vx = vx + 0.5 * (ax + ax_new) * dt
        vy = vy + 0.5 * (ay + ay_new) * dt
        x, y = x_new, y_new
        ax, ay = ax_new, ay_new
    return positions


def hooke_positions(*, steps: int, dt: float, ax: float, ay: float, w: float, phase: float = 0.0) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for k in range(steps):
        t = k * dt
        out.append((ax * math.cos(w * t + phase), ay * math.sin(w * t + phase)))
    return out


def constant_velocity_positions(
    *, steps: int, dt: float, x0: float, y0: float, vx: float, vy: float
) -> list[tuple[float, float]]:
    return [(x0 + vx * dt * k, y0 + vy * dt * k) for k in range(steps)]


def add_noise(
    positions: list[tuple[float, float]], *, sigma: float, seed: int = 0
) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    return [(x + rng.uniform(-sigma, sigma), y + rng.uniform(-sigma, sigma)) for x, y in positions]


def run_campaign(
    *,
    tmp_path: Path,
    positions: dict[str, list[tuple[float, float]]],
    dt: float = DEFAULT_DT,
    dev_fraction: float = 0.5,
) -> SASScienceState:
    repo_root = REPO_ROOT
    run_root = tmp_path / "run"
    control_dir = run_root / "state" / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    # enable flags
    (control_dir / "ENABLE_RESEARCH").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_SAS_SCIENCE").write_text("enable", encoding="utf-8")
    write_canon_json(control_dir / "SAS_SCIENCE_LEASE.json", {"lease_id": "fixture"})

    bodies = list(positions.keys())
    manifest = build_manifest(bodies=bodies, dev_fraction=dev_fraction)
    times = [k * dt for k in range(len(next(iter(positions.values()))))]
    csv_path, manifest_path = write_dataset(tmp_path=tmp_path, manifest=manifest, times=times, positions=positions)

    pack_path = repo_root / "campaigns" / "rsi_sas_science_v13_0" / "rsi_sas_science_pack_v1.json"

    agi_root = tmp_path / "agi_root"
    agi_root.mkdir(parents=True, exist_ok=True)
    old_agi_root = os.environ.get("AGI_ROOT")
    os.environ["AGI_ROOT"] = str(agi_root)
    try:
        result = run_sas_science(
            dataset_csv=csv_path,
            dataset_manifest=manifest_path,
            campaign_pack=pack_path,
            state_dir=run_root,
        )
    finally:
        if old_agi_root is None:
            os.environ.pop("AGI_ROOT", None)
        else:
            os.environ["AGI_ROOT"] = old_agi_root

    return SASScienceState(
        run_root=run_root,
        state_dir=run_root / "state",
        result=result,
        manifest_path=manifest_path,
        csv_path=csv_path,
    )


def load_selected_ir(state: SASScienceState) -> dict[str, Any]:
    theory_id = state.result.get("selected_theory_id")
    ir_path = state.state_dir / "theory" / "ir" / f"sha256_{theory_id.split(':',1)[1]}.sas_science_theory_ir_v1.json"
    return load_canon_json(ir_path)


def load_promotion_bundle(state: SASScienceState) -> dict[str, Any]:
    promo_path = Path(state.result.get("promotion_bundle", ""))
    return load_canon_json(promo_path)
