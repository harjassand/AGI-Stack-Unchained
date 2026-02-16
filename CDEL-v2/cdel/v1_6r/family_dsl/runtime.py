"""Family DSL runtime for v1.5r."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..canon import CanonError, canon_bytes, hash_json, sha256_prefixed
from ..constants import require_constants


@dataclass(frozen=True)
class EvalContext:
    """Evaluation context for family DSL."""

    family_id: str
    theta: dict[str, Any]
    theta0: dict[str, Any]
    epoch_commitment: str
    key_material: bytes


def compute_family_id(family: dict[str, Any]) -> str:
    data = dict(family)
    data.pop("family_id", None)
    return hash_json(data)


def _theta0_from_schema(params_schema: list[dict[str, Any]]) -> dict[str, Any]:
    theta0: dict[str, Any] = {}
    for param in params_schema:
        name = param.get("name")
        if not isinstance(name, str):
            raise ValueError("param name missing for theta0")
        ptype = param.get("type")
        min_val = param.get("min")
        if ptype == "int":
            if not isinstance(min_val, int):
                raise ValueError(f"param {name} missing int min for theta0")
            theta0[name] = int(min_val)
        elif ptype == "fixed":
            if not isinstance(min_val, str):
                raise ValueError(f"param {name} missing fixed min for theta0")
            theta0[name] = min_val
        else:
            raise ValueError(f"unknown param type for theta0: {ptype}")
    return theta0


def _parse_prefixed_hash(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("hash value missing")
    hex_part = value.split(":", 1)[1] if ":" in value else value
    return bytes.fromhex(hex_part)


@lru_cache(maxsize=1)
def _probe_keys() -> tuple[str, str, bytes, bytes]:
    constants = require_constants()
    sem = constants.get("family_semantics", {})
    key_a = sem.get("probe_key_a")
    key_b = sem.get("probe_key_b")
    if not isinstance(key_a, str) or not isinstance(key_b, str):
        raise ValueError("missing family_semantics probe keys in constants")
    return key_a, key_b, _parse_prefixed_hash(key_a), _parse_prefixed_hash(key_b)


def _editworld_vocab(vocab_id: str) -> list[str]:
    constants = require_constants()
    editworld = constants.get("editworld", {})
    vocabs = editworld.get("vocabs", {})
    if not isinstance(vocabs, dict):
        raise ValueError("editworld vocabs missing")
    vocab = vocabs.get(vocab_id)
    if not isinstance(vocab, list) or not all(isinstance(tok, str) for tok in vocab):
        raise ValueError("editworld vocab invalid")
    return vocab


def _editworld_max_goal_len() -> int:
    constants = require_constants()
    editworld = constants.get("editworld", {})
    max_goal_len = editworld.get("max_goal_len")
    if not isinstance(max_goal_len, int):
        raise ValueError("editworld max_goal_len missing")
    return max_goal_len


def _hash_mod16(value: Any) -> int:
    return hashlib.sha256(canon_bytes(value)).digest()[0] % 16


def _suite_row_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        suite_row = payload.get("suite_row")
        if isinstance(suite_row, dict):
            return suite_row
    return {}


def _semantic_signature_fields(suite_row: dict[str, Any]) -> dict[str, int]:
    env_kind = suite_row.get("env", "unknown")
    if not isinstance(env_kind, str):
        env_kind = "unknown"
    max_steps = suite_row.get("max_steps", 0)
    if not isinstance(max_steps, int):
        max_steps = 0
    env_bucket = _hash_mod16(env_kind)
    max_steps_bucket = int(max_steps) % 16
    if env_kind == "gridworld-v1":
        walls = suite_row.get("walls", [])
        wall_list = []
        if isinstance(walls, list):
            for item in walls:
                if isinstance(item, dict):
                    x = int(item.get("x", 0))
                    y = int(item.get("y", 0))
                    wall_list.append({"x": x, "y": y})
        wall_list = sorted(wall_list, key=lambda w: (w["x"], w["y"]))
        structure_bucket = _hash_mod16(wall_list)
        detail_bucket = _hash_mod16(
            {
                "start": suite_row.get("start"),
                "goal": suite_row.get("goal"),
                "walls": wall_list,
            }
        )
    elif env_kind == "lineworld-v1":
        walls = suite_row.get("walls", [])
        wall_list = sorted([int(w) for w in walls if isinstance(w, int)])
        structure_bucket = _hash_mod16(wall_list)
        detail_bucket = _hash_mod16(
            {
                "start": suite_row.get("start"),
                "goal": suite_row.get("goal"),
                "length": suite_row.get("length"),
                "walls": wall_list,
                "slip_p": suite_row.get("slip_p"),
            }
        )
    elif env_kind == "editworld-v1":
        structure_bucket = _hash_mod16(
            {
                "vocab_id": suite_row.get("vocab_id"),
                "obs_window": suite_row.get("obs_window"),
            }
        )
        detail_bucket = _hash_mod16(
            {
                "start_text": suite_row.get("start_text"),
                "goal_text": suite_row.get("goal_text"),
                "slip_ppm": suite_row.get("slip_ppm"),
                "start_cursor": suite_row.get("start_cursor"),
            }
        )
    else:
        structure_bucket = _hash_mod16([])
        detail_bucket = _hash_mod16([])
    return {
        "obs_class": env_bucket,
        "nuisance_class": max_steps_bucket,
        "action_remap_class": structure_bucket,
        "delay_class": detail_bucket,
        "noise_class": 0,
        "render_class": 0,
    }


def _semantic_id_for_signature(family: dict[str, Any]) -> str:
    payload = dict(family)
    payload.pop("signature", None)
    payload.pop("family_id", None)
    return hash_json(payload)


def compute_signature(family: dict[str, Any]) -> dict[str, Any]:
    theta0 = _theta0_from_schema(family.get("params_schema", []))
    key_a, _key_b, key_a_bytes, _key_b_bytes = _probe_keys()
    semantic_id = _semantic_id_for_signature(family)
    ctx = EvalContext(
        family_id=semantic_id,
        theta=theta0,
        theta0=theta0,
        epoch_commitment=key_a,
        key_material=key_a_bytes,
    )
    payload = eval_ast(family.get("instantiator", {}), ctx)
    suite_row = _suite_row_from_payload(payload)
    fields = _semantic_signature_fields(suite_row)
    return {
        "schema": "family_signature_v1",
        "schema_version": 1,
        "signature_version": 1,
        "fields": fields,
    }


def _parse_decimal(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError("invalid decimal string") from exc
    raise ValueError("invalid numeric value")


def validate_theta(params_schema: list[dict[str, Any]], theta: dict[str, Any]) -> None:
    for param in params_schema:
        name = param.get("name")
        if name not in theta:
            raise ValueError(f"missing theta param: {name}")
        ptype = param.get("type")
        value = theta[name]
        min_val = param.get("min")
        max_val = param.get("max")
        step = param.get("step")
        if ptype == "int":
            if not isinstance(value, int):
                raise ValueError(f"param {name} must be int")
            if not isinstance(min_val, int) or not isinstance(max_val, int) or not isinstance(step, int):
                raise ValueError(f"param schema for {name} must use int bounds")
            if value < min_val or value > max_val:
                raise ValueError(f"param {name} out of range")
            if ((value - min_val) % step) != 0:
                raise ValueError(f"param {name} not aligned to step")
        elif ptype == "fixed":
            if not isinstance(value, str):
                raise ValueError(f"param {name} must be fixed-point string")
            min_f = _parse_decimal(min_val)
            max_f = _parse_decimal(max_val)
            step_f = _parse_decimal(step)
            val_f = _parse_decimal(value)
            if val_f < min_f or val_f > max_f:
                raise ValueError(f"param {name} out of range")
            # step check with tolerance; fixed values are strings so this is best-effort
            if step_f <= 0:
                raise ValueError(f"param {name} step must be > 0")
        else:
            raise ValueError(f"unknown param type: {ptype}")


def validate_family(family: dict[str, Any]) -> None:
    if family.get("schema") != "family_dsl_v1":
        raise ValueError("family schema mismatch")
    if family.get("schema_version") != 1:
        raise ValueError("family schema_version mismatch")
    if family.get("dsl_version") != 1:
        raise ValueError("family dsl_version mismatch")
    expected = compute_family_id(family)
    if family.get("family_id") != expected:
        raise ValueError("family_id mismatch")
    expected_sig = compute_signature(family)
    if family.get("signature") != expected_sig:
        raise ValueError("family signature mismatch")


def validate_family_relaxed(family: dict[str, Any]) -> None:
    if family.get("schema") != "family_dsl_v1":
        raise ValueError("family schema mismatch")
    if family.get("schema_version") != 1:
        raise ValueError("family schema_version mismatch")
    if family.get("dsl_version") != 1:
        raise ValueError("family dsl_version mismatch")
    expected = compute_family_id(family)
    if family.get("family_id") != expected:
        raise ValueError("family_id mismatch")


def _to_bytes(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return canon_bytes(value)


def _u32_from_bytes(data: bytes) -> int:
    if len(data) < 4:
        raise ValueError("u32 requires at least 4 bytes")
    return int.from_bytes(data[:4], byteorder="little", signed=False)


def _range_int(u32_value: int, min_val: int, max_val: int) -> int:
    if min_val > max_val:
        raise ValueError("min must be <= max")
    span = max_val - min_val + 1
    limit = (1 << 32) // span * span
    while True:
        if u32_value < limit:
            return min_val + (u32_value % span)
        u32_value = (u32_value + 1) % (1 << 32)


def _rotate_left(value: int, shift: int) -> int:
    return ((value << shift) & 0xFFFFFFFF) | (value >> (32 - shift))


def _quarter_round(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] ^= state[a]
    state[d] = _rotate_left(state[d], 16)

    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] ^= state[c]
    state[b] = _rotate_left(state[b], 12)

    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] ^= state[a]
    state[d] = _rotate_left(state[d], 8)

    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] ^= state[c]
    state[b] = _rotate_left(state[b], 7)


def _chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("ChaCha20 key must be 32 bytes")
    if len(nonce) != 12:
        raise ValueError("ChaCha20 nonce must be 12 bytes")
    constants = b"expand 32-byte k"
    state = [
        int.from_bytes(constants[0:4], "little"),
        int.from_bytes(constants[4:8], "little"),
        int.from_bytes(constants[8:12], "little"),
        int.from_bytes(constants[12:16], "little"),
    ]
    state += [int.from_bytes(key[i : i + 4], "little") for i in range(0, 32, 4)]
    state.append(counter & 0xFFFFFFFF)
    state += [int.from_bytes(nonce[i : i + 4], "little") for i in range(0, 12, 4)]

    working = state.copy()
    for _ in range(10):
        _quarter_round(working, 0, 4, 8, 12)
        _quarter_round(working, 1, 5, 9, 13)
        _quarter_round(working, 2, 6, 10, 14)
        _quarter_round(working, 3, 7, 11, 15)
        _quarter_round(working, 0, 5, 10, 15)
        _quarter_round(working, 1, 6, 11, 12)
        _quarter_round(working, 2, 7, 8, 13)
        _quarter_round(working, 3, 4, 9, 14)

    out = [(working[i] + state[i]) & 0xFFFFFFFF for i in range(16)]
    return b"".join(x.to_bytes(4, "little") for x in out)


def _chacha20_stream(seed: bytes, n_bytes: int) -> bytes:
    key = seed
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    nonce = b"\x00" * 12
    counter = 0
    out = bytearray()
    while len(out) < n_bytes:
        out.extend(_chacha20_block(key, counter, nonce))
        counter = (counter + 1) & 0xFFFFFFFF
    return bytes(out[:n_bytes])


def _xorshift128plus_seed(seed: bytes) -> tuple[int, int]:
    digest = hashlib.sha256(seed).digest()
    s0 = int.from_bytes(digest[:8], "little")
    s1 = int.from_bytes(digest[8:16], "little")
    if s0 == 0 and s1 == 0:
        s1 = 0x9E3779B97F4A7C15
    return s0 & 0xFFFFFFFFFFFFFFFF, s1 & 0xFFFFFFFFFFFFFFFF


def _xorshift128plus_next(state: tuple[int, int]) -> tuple[int, tuple[int, int]]:
    s0, s1 = state
    x = s0
    y = s1
    s0 = y
    x ^= (x << 23) & 0xFFFFFFFFFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFFFFFFFFFF
    x ^= y
    x ^= (y >> 26) & 0xFFFFFFFFFFFFFFFF
    s1 = x & 0xFFFFFFFFFFFFFFFF
    result = (s0 + s1) & 0xFFFFFFFFFFFFFFFF
    return result, (s0, s1)


def _keyed_seed(ctx: EvalContext, tag: str) -> bytes:
    tag_bytes = tag.encode("utf-8")
    return hashlib.sha256(ctx.key_material + ctx.family_id.encode("utf-8") + canon_bytes(ctx.theta0) + tag_bytes).digest()


def _range_int_u64(value: int, min_val: int, max_val: int) -> int:
    if min_val > max_val:
        raise ValueError("min must be <= max")
    span = max_val - min_val + 1
    limit = (1 << 64) // span * span
    v = value & 0xFFFFFFFFFFFFFFFF
    while v >= limit:
        v = (v + 1) & 0xFFFFFFFFFFFFFFFF
    return min_val + (v % span)


def eval_ast(node: dict[str, Any], ctx: EvalContext) -> Any:
    op = node.get("op")
    if op == "CONST":
        return node.get("value")
    if op == "PARAM":
        name = node.get("name")
        if name not in ctx.theta:
            raise ValueError(f"unknown param: {name}")
        return ctx.theta[name]
    if op == "BYTES":
        parts = node.get("parts", [])
        return b"".join(_to_bytes(eval_ast(part, ctx)) for part in parts)
    if op == "SHA256":
        data = _to_bytes(eval_ast(node.get("x"), ctx))
        return hashlib.sha256(data).digest()
    if op == "PRNG_CHACHA20":
        seed = _to_bytes(eval_ast(node.get("seed"), ctx))
        n_bytes = int(node.get("n_bytes"))
        return _chacha20_stream(seed, n_bytes)
    if op == "U32_LE":
        data = _to_bytes(eval_ast(node.get("x"), ctx))
        return _u32_from_bytes(data)
    if op == "RANGE_INT":
        u32_value = eval_ast(node.get("u32"), ctx)
        if not isinstance(u32_value, int):
            raise ValueError("u32 must be int")
        return _range_int(u32_value, int(node.get("min")), int(node.get("max")))
    if op == "KEYED_RAND_INT_V1":
        min_val = int(node.get("min"))
        max_val = int(node.get("max"))
        tag = node.get("tag")
        if not isinstance(tag, str):
            raise ValueError("KEYED_RAND_INT_V1 tag must be string")
        seed = _keyed_seed(ctx, tag)
        state = _xorshift128plus_seed(seed)
        value, _state = _xorshift128plus_next(state)
        return _range_int_u64(value, min_val, max_val)
    if op == "KEYED_RAND_CHOICE_V1":
        choices = node.get("choices")
        tag = node.get("tag")
        if not isinstance(tag, str):
            raise ValueError("KEYED_RAND_CHOICE_V1 tag must be string")
        if not isinstance(choices, list) or not choices:
            raise ValueError("KEYED_RAND_CHOICE_V1 choices must be non-empty list")
        seed = _keyed_seed(ctx, tag)
        state = _xorshift128plus_seed(seed)
        value, _state = _xorshift128plus_next(state)
        idx = _range_int_u64(value, 0, len(choices) - 1)
        return choices[idx]
    if op == "KEYED_RAND_STR_V1":
        vocab_id = node.get("vocab_id")
        min_len = int(node.get("min_len"))
        max_len = int(node.get("max_len"))
        tag = node.get("tag")
        if not isinstance(tag, str):
            raise ValueError("KEYED_RAND_STR_V1 tag must be string")
        if not isinstance(vocab_id, str):
            raise ValueError("KEYED_RAND_STR_V1 vocab_id must be string")
        if max_len < min_len or min_len < 0:
            raise ValueError("KEYED_RAND_STR_V1 length bounds invalid")
        vocab = _editworld_vocab(vocab_id)
        seed = _keyed_seed(ctx, tag)
        state = _xorshift128plus_seed(seed)
        value, state = _xorshift128plus_next(state)
        length = _range_int_u64(value, min_len, max_len)
        out: list[str] = []
        for _ in range(int(length)):
            value, state = _xorshift128plus_next(state)
            idx = _range_int_u64(value, 0, len(vocab) - 1)
            out.append(vocab[idx])
        return "".join(out)
    if op == "LINEWORLD_BUILD_V1":
        length = int(eval_ast(node.get("length"), ctx))
        start = int(eval_ast(node.get("start"), ctx)) if node.get("start") is not None else 0
        goal = int(eval_ast(node.get("goal"), ctx))
        walls_k = int(eval_ast(node.get("walls_k"), ctx))
        max_steps = int(eval_ast(node.get("max_steps"), ctx))
        slip_ppm = int(eval_ast(node.get("slip_ppm"), ctx))
        if length < 0 or max_steps <= 0:
            raise ValueError("lineworld length/max_steps invalid")
        if start < 0 or start > length or goal < 0 or goal > length:
            raise ValueError("lineworld start/goal out of bounds")
        if slip_ppm < 0 or slip_ppm > 1_000_000:
            raise ValueError("lineworld slip_ppm out of bounds")
        low = min(start, goal)
        high = max(start, goal)
        available = [
            pos
            for pos in range(0, length + 1)
            if pos not in {start, goal} and (pos < low or pos > high)
        ]
        walls_k = max(0, min(int(walls_k), len(available)))
        seed = _keyed_seed(ctx, "lineworld_walls")
        state = _xorshift128plus_seed(seed)
        walls: list[int] = []
        while len(walls) < walls_k and available:
            value, state = _xorshift128plus_next(state)
            idx = _range_int_u64(value, 0, len(available) - 1)
            walls.append(available.pop(idx))
        walls.sort()
        return {
            "suite_row": {
                "env": "lineworld-v1",
                "max_steps": max_steps,
                "length": length,
                "start": start,
                "goal": goal,
                "walls": walls,
                "slip_p": slip_ppm,
            }
        }
    if op == "GRIDWORLD_BUILD_V1":
        width = int(eval_ast(node.get("width"), ctx))
        height = int(eval_ast(node.get("height"), ctx))
        start = eval_ast(node.get("start"), ctx)
        goal = eval_ast(node.get("goal"), ctx)
        walls_k = int(eval_ast(node.get("walls_k"), ctx))
        max_steps = int(eval_ast(node.get("max_steps"), ctx))
        if width < 0 or height < 0 or max_steps <= 0:
            raise ValueError("gridworld width/height/max_steps invalid")
        if not isinstance(start, dict) or not isinstance(goal, dict):
            raise ValueError("gridworld start/goal must be objects")
        sx, sy = int(start.get("x", 0)), int(start.get("y", 0))
        gx, gy = int(goal.get("x", 0)), int(goal.get("y", 0))
        if sx < 0 or sy < 0 or gx < 0 or gy < 0:
            raise ValueError("gridworld start/goal must be non-negative")
        if sx > width or gx > width or sy > height or gy > height:
            raise ValueError("gridworld start/goal out of bounds")
        blocked_rows = {sy, gy}
        available = [
            (x, y)
            for x in range(width + 1)
            for y in range(height + 1)
            if (x, y) not in {(sx, sy), (gx, gy)} and y not in blocked_rows
        ]
        walls_k = max(0, min(int(walls_k), len(available)))
        seed = _keyed_seed(ctx, "gridworld_walls")
        state = _xorshift128plus_seed(seed)
        walls: list[dict[str, int]] = []
        while len(walls) < walls_k and available:
            value, state = _xorshift128plus_next(state)
            idx = _range_int_u64(value, 0, len(available) - 1)
            x, y = available.pop(idx)
            walls.append({"x": x, "y": y})
        walls.sort(key=lambda w: (w["x"], w["y"]))
        return {
            "suite_row": {
                "env": "gridworld-v1",
                "max_steps": max_steps,
                "start": {"x": sx, "y": sy},
                "goal": {"x": gx, "y": gy},
                "walls": walls,
            }
        }
    if op == "EDITWORLD_BUILD_V1":
        max_steps = int(eval_ast(node.get("max_steps"), ctx))
        vocab_id = eval_ast(node.get("vocab_id"), ctx)
        goal_text = eval_ast(node.get("goal_text"), ctx)
        k_edits = int(eval_ast(node.get("k_edits"), ctx))
        slip_ppm = int(eval_ast(node.get("slip_ppm"), ctx))
        obs_window = int(eval_ast(node.get("obs_window"), ctx))
        if not isinstance(vocab_id, str) or not isinstance(goal_text, str):
            raise ValueError("editworld vocab_id/goal_text invalid")
        if max_steps <= 0:
            raise ValueError("editworld max_steps invalid")
        if k_edits < 0:
            raise ValueError("editworld k_edits invalid")
        if slip_ppm < 0 or slip_ppm > 1_000_000:
            raise ValueError("editworld slip_ppm invalid")
        if obs_window < 0:
            raise ValueError("editworld obs_window invalid")
        vocab = _editworld_vocab(vocab_id)
        max_goal_len = _editworld_max_goal_len()
        if len(goal_text) > max_goal_len:
            raise ValueError("editworld goal_text too long")

        text = list(goal_text)
        seed = _keyed_seed(ctx, "edits")
        state = _xorshift128plus_seed(seed)
        ops = ["INSERT", "DELETE", "SUBSTITUTE"]
        for _ in range(k_edits):
            value, state = _xorshift128plus_next(state)
            op = ops[_range_int_u64(value, 0, len(ops) - 1)]
            if op == "DELETE" and not text:
                op = "INSERT"
            if op == "SUBSTITUTE" and not text:
                op = "INSERT"
            if op == "INSERT" and len(text) >= max_goal_len:
                op = "SUBSTITUTE" if text else "INSERT"
            if op == "INSERT":
                value, state = _xorshift128plus_next(state)
                pos = _range_int_u64(value, 0, len(text))
                value, state = _xorshift128plus_next(state)
                tok = vocab[_range_int_u64(value, 0, len(vocab) - 1)]
                text.insert(pos, tok)
            elif op == "DELETE":
                value, state = _xorshift128plus_next(state)
                pos = _range_int_u64(value, 0, len(text) - 1)
                text.pop(pos)
            elif op == "SUBSTITUTE":
                value, state = _xorshift128plus_next(state)
                pos = _range_int_u64(value, 0, len(text) - 1)
                value, state = _xorshift128plus_next(state)
                tok = vocab[_range_int_u64(value, 0, len(vocab) - 1)]
                text[pos] = tok

        start_text = "".join(text)
        cursor_seed = _keyed_seed(ctx, "cursor")
        cursor_state = _xorshift128plus_seed(cursor_seed)
        cursor_val, _cursor_state = _xorshift128plus_next(cursor_state)
        start_cursor = _range_int_u64(cursor_val, 0, len(start_text))

        return {
            "suite_row": {
                "env": "editworld-v1",
                "max_steps": max_steps,
                "vocab_id": vocab_id,
                "goal_text": goal_text,
                "start_text": start_text,
                "start_cursor": int(start_cursor),
                "slip_ppm": slip_ppm,
                "obs_window": obs_window,
            }
        }
    if op == "EMIT_INSTANCE":
        return eval_ast(node.get("instance_spec"), ctx)
    raise ValueError(f"unknown op: {op}")


def instantiate_family(
    family: dict[str, Any],
    theta: dict[str, Any],
    epoch_commit: dict[str, Any],
    *,
    epoch_key: bytes | None = None,
    skip_validation: bool = False,
) -> dict[str, Any]:
    if skip_validation:
        validate_family_relaxed(family)
    else:
        validate_family(family)
    validate_theta(family.get("params_schema", []), theta)
    epoch_commitment = epoch_commit.get("commitment")
    if not isinstance(epoch_commitment, str):
        raise ValueError("epoch_commitment missing")
    theta0 = _theta0_from_schema(family.get("params_schema", []))
    if epoch_key is None:
        try:
            key_material = _parse_prefixed_hash(epoch_commitment)
        except Exception:
            key_material = hashlib.sha256(epoch_commitment.encode("utf-8")).digest()
    else:
        key_material = epoch_key
    ctx = EvalContext(
        family_id=family["family_id"],
        theta=theta,
        theta0=theta0,
        epoch_commitment=epoch_commitment,
        key_material=key_material,
    )
    payload = eval_ast(family["instantiator"], ctx)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    inst_hash_payload = {
        "family_id": family["family_id"],
        "theta": theta,
        "epoch_commitment": epoch_commitment,
        "dsl_version": 1,
    }
    inst_hash = sha256_prefixed(canon_bytes(inst_hash_payload))
    return {
        "schema": "instance_spec_v1",
        "schema_version": 1,
        "family_id": family["family_id"],
        "theta": theta,
        "epoch_commitment": epoch_commitment,
        "inst_hash": inst_hash,
        "payload": payload,
    }
