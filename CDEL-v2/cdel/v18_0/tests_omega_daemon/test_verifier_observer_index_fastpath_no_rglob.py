from __future__ import annotations

from pathlib import Path

from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier
from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, hash_file_stream, load_canon_dict
from cdel.v18_0.omega_observer_index_v1 import load_index
from cdel.v18_0.verify_rsi_omega_daemon_v1 import verify
from .utils import latest_file, load_json, run_tick_once


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _find_matching_artifact(root: Path, source: dict[str, object]) -> Path:
    schema_id = str(source.get("schema_id", ""))
    artifact_hash = str(source.get("artifact_hash", ""))

    fixed_rel = verifier._OBS_SOURCE_FIXED_PATH_REL.get(schema_id)  # noqa: SLF001
    if fixed_rel is not None:
        fixed_path = root / fixed_rel
        if not fixed_path.is_file():
            raise FileNotFoundError(f"no fixed artifact found for schema_id={schema_id}")
        if schema_id == "polymath_void_report_v1":
            if hash_file_stream(fixed_path) != artifact_hash:
                raise FileNotFoundError(f"artifact hash mismatch for schema_id={schema_id}")
            return fixed_path
        try:
            payload = load_canon_dict(fixed_path)
        except OmegaV18Error as exc:
            raise FileNotFoundError(f"invalid fixed artifact for schema_id={schema_id}") from exc
        if canon_hash_obj(payload) != artifact_hash:
            raise FileNotFoundError(f"artifact hash mismatch for schema_id={schema_id}")
        return fixed_path

    suffix = verifier._OBS_SOURCE_SUFFIX.get(schema_id)  # noqa: SLF001
    if suffix is None:
        raise FileNotFoundError(f"unknown source schema_id={schema_id}")
    artifact_hex = artifact_hash.split(":", 1)[1]
    filename = f"sha256_{artifact_hex}.{suffix}"
    producer_run_id = str(source.get("producer_run_id", ""))

    index_entry = (load_index(root).get("entries") or {}).get(schema_id)
    if isinstance(index_entry, dict):
        path_rel = str(index_entry.get("path_rel", "")).strip()
        if path_rel:
            candidate = (root / path_rel).resolve()
            if candidate.is_file():
                try:
                    payload = load_canon_dict(candidate)
                except OmegaV18Error:
                    payload = None
                if isinstance(payload, dict) and canon_hash_obj(payload) == artifact_hash:
                    return candidate

    runs_root = root / "runs"
    candidates: list[Path] = []
    if producer_run_id:
        run_dir = runs_root / producer_run_id
        if run_dir.is_dir():
            candidates.extend(sorted(run_dir.glob(f"**/{filename}")))
        if not candidates:
            candidates.extend(sorted(runs_root.glob(f"{producer_run_id}*/**/{filename}")))
        if not candidates:
            candidates.extend(sorted(runs_root.glob(f"**/{producer_run_id}/**/{filename}")))
    if not candidates:
        candidates.extend(sorted(runs_root.glob(f"**/{filename}")))

    for candidate in sorted(set(candidates), key=lambda path: path.as_posix()):
        try:
            payload = load_canon_dict(candidate)
        except OmegaV18Error:
            continue
        if canon_hash_obj(payload) == artifact_hash:
            return candidate

    pattern = f"**/*.{suffix}"
    for candidate in sorted(runs_root.glob(pattern), key=lambda path: path.as_posix()):
        if not candidate.is_file():
            continue
        try:
            payload = load_canon_dict(candidate)
        except OmegaV18Error:
            continue
        if canon_hash_obj(payload) == artifact_hash:
            return candidate

    raise FileNotFoundError(f"no source artifact found for schema_id={schema_id}")


def test_verifier_observer_index_fastpath_no_rglob(tmp_path, monkeypatch) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    obs_hash = str(snapshot["observation_report_hash"]).split(":", 1)[1]
    observation_path = state_dir / "observations" / f"sha256_{obs_hash}.omega_observation_report_v1.json"
    observation = load_json(observation_path)
    sources = observation.get("sources")
    assert isinstance(sources, list) and sources

    root = _repo_root()
    entries: dict[str, dict[str, str]] = {}
    for source in sources:
        assert isinstance(source, dict)
        schema_id = str(source.get("schema_id", ""))
        path = _find_matching_artifact(root, source)
        entries[schema_id] = {"path_rel": path.relative_to(root).as_posix()}

    index = {"schema_version": "omega_observer_index_v1", "entries": entries}
    monkeypatch.setattr(verifier, "load_index", lambda _root: index)

    def _forbid_rglob(self: Path, pattern: str):  # noqa: ARG001
        raise AssertionError("verifier used Path.rglob fallback")

    monkeypatch.setattr(Path, "rglob", _forbid_rglob)

    assert verify(state_dir, mode="full") == "VALID"
