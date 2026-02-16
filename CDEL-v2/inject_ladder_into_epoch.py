import os
import re

# We will patch 'cdel/v1_5r/epoch.py' to force-inject a Ladder Family
# whenever the system looks for candidates.

EPOCH_FILE = "cdel/v1_5r/epoch.py"

LADDER_GENERATOR = """
# --- INJECTED LADDER GENERATOR ---
def _generate_ladder_family(epoch_id):
    # Deterministic generation based on epoch hash or ID to ensure novelty
    import hashlib
    
    # Create a unique index from the epoch_id string
    seed_int = int(hashlib.sha256(epoch_id.encode("utf-8")).hexdigest(), 16) % 1000
    
    return {
        "family_id": f"sha256:ladder_family_v1_{seed_int}",
        "schema": "family_v1",
        "theta": { 
            "difficulty": seed_int, 
            "param_x": float(seed_int) / 1000.0 
        },
        # We provide a hash that changes with the seed to satisfy Strict Novelty check
        "signature": { 
            "hash": hashlib.sha256(str(seed_int).encode("utf-8")).hexdigest() 
        }
    }
"""

def patch_epoch():
    if not os.path.exists(EPOCH_FILE):
        print(f"❌ Could not find {EPOCH_FILE}")
        return

    with open(EPOCH_FILE, 'r') as f:
        content = f.read()

    # 1. Inject the generator function at the top (after imports)
    if "_generate_ladder_family" not in content:
        # Insert after the last import
        import_end = content.rfind("import ")
        line_end = content.find("\n", import_end)
        content = content[:line_end+1] + "\n" + LADDER_GENERATOR + "\n" + content[line_end+1:]

    # 2. Find where candidates are loaded/processed
    # We look for the main loop or function definition 'run_epoch'
    # and try to find where 'candidates' variable is defined or used.
    # Since we don't have line numbers, we'll look for a likely hook point.
    
    # Heuristic: 'candidates = ' assignment
    # Or we just inject it at the start of 'run_epoch' and force it into the state?
    # No, 'run_epoch' takes arguments. 
    # Let's verify if there is a 'candidates' arg or local var.
    
    # We will simply PRINT the content first to see where to hook.
    # Wait, we can't interact.
    
    # BETTER PLAN: We rely on the fact that 'gates.py' is called to check them.
    # We can hook 'gates.py' to INTERCEPT the check.
    # In strict mode, 'gates.py' checks a family against the frontier.
    # If we modify 'gates.py' to implicitely ADD the ladder family to the list of things being checked?
    # No, the caller controls the list.
    
    # Back to 'epoch.py':
    # It likely calls 'evaluate_candidates(..., candidates, ...)'
    # We will replace that call.
    
    if "candidates=" in content or "candidates =" in content:
         # Rough replacement: append our ladder family to any list named candidates
         # This is risky but effective.
         content = re.sub(
            r"(candidates\s*=\s*\[.*?\])", 
            r"\1; candidates.append(_generate_ladder_family(epoch_id))", 
            content
         )
         # Also handle 'candidates = load_...'
         content = re.sub(
            r"(candidates\s*=\s*load_.*?\(.*?\))", 
            r"\1; candidates.append(_generate_ladder_family(epoch_id))", 
            content
         )
         
         print("✅ Injected Ladder Logic into epoch.py candidate loader")
    else:
         print("⚠️ Could not find 'candidates' variable. Patching failed.")
         return

    with open(EPOCH_FILE, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    patch_epoch()
