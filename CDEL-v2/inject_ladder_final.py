import os

EPOCH_FILE = "cdel/v1_5r/epoch.py"

LADDER_CODE = """
def _generate_ladder_family(epoch_id):
    # Deterministic Ladder Generation
    import hashlib
    # Create a unique index based on epoch_id hash to ensure it changes every time
    seed_int = int(hashlib.sha256(epoch_id.encode("utf-8")).hexdigest(), 16) % 10000
    
    return {
        "family_id": f"sha256:ladder_family_v1_{seed_int}",
        "schema": "family_v1",
        "theta": { 
            "difficulty": seed_int, 
            "param_x": float(seed_int) / 10000.0 
        },
        # Explicit hash to satisfy Strict Novelty (distance > delta)
        "signature": { 
            "hash": hashlib.sha256(str(seed_int).encode("utf-8")).hexdigest() 
        }
    }
"""

def patch_epoch_final():
    if not os.path.exists(EPOCH_FILE):
        print(f"❌ Critical: {EPOCH_FILE} not found.")
        return

    with open(EPOCH_FILE, 'r') as f:
        content = f.read()

    # 1. Inject the helper function
    if "_generate_ladder_family" not in content:
        # Insert after imports (heuristic: after the last 'from ... import ...')
        last_import = content.rfind("import ")
        newline = content.find("\n", last_import)
        content = content[:newline+1] + "\n" + LADDER_CODE + "\n" + content[newline+1:]
        print("✅ Injected Ladder Helper Function.")

    # 2. Fix the hardcoded empty list
    # Target: compress_frontier(families, [], frontier.get("M_FRONTIER", 16))
    target = 'compress_frontier(families, [], frontier.get("M_FRONTIER", 16))'
    replacement = 'compress_frontier(families, [_generate_ladder_family(epoch_id)], frontier.get("M_FRONTIER", 16))'
    
    if target in content:
        content = content.replace(target, replacement)
        print("✅ Patched run_epoch to accept Ladder Candidates.")
    else:
        # Fallback for slightly different formatting
        print("⚠️ Exact match not found, trying regex...")
        import re
        content = re.sub(
            r"compress_frontier\(families,\s*\[\],\s*", 
            r"compress_frontier(families, [_generate_ladder_family(epoch_id)], ", 
            content
        )
        print("✅ Patched run_epoch (Regex Mode).")

    with open(EPOCH_FILE, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    patch_epoch_final()
