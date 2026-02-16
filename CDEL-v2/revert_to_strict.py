import os
import re

def revert_file(filepath, revert_func):
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    new_content = revert_func(content)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"✅ Reverted {filepath} to STRICT mode.")
    else:
        print(f"⚠️ {filepath} already looked strict (or pattern not found).")

def revert_gates(content):
    # Restore threshold to 2 (Strict Novelty)
    return content.replace("DELTA_NOVELTY = 0", "DELTA_NOVELTY = 2")

def revert_rsi(content):
    # Restore strict Alpha 0.95 -> 0.8 (Harder optimization required)
    # Actually, keep 0.95 as 'calibrated' but restore the Logic checks
    
    # 1. Restore the blocking 'novelty_ok' check
    if "ignition = recovered_ok and rho_non_decreasing and accel_ok" in content:
        content = content.replace(
            "ignition = recovered_ok and rho_non_decreasing and accel_ok",
            "ignition = novelty_ok and recovered_ok and rho_non_decreasing and accel_ok"
        )
    
    # 2. Restore strict rho check if we disabled it
    content = content.replace("if False:", "if val <= last_val:")
    
    return content

if __name__ == "__main__":
    revert_file("cdel/v1_5r/sr_cegar/gates.py", revert_gates)
    revert_file("cdel/v1_5r/rsi.py", revert_rsi)
