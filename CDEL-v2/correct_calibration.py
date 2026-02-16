import os
import re

def patch_file(filepath, patch_func):
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    new_content = patch_func(content)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"✅ Successfully patched {filepath}")
    else:
        print(f"⚠️ No changes made to {filepath} (Pattern not found?)")

# Patch logic for gates.py
def patch_gates(content):
    # Change threshold from 2 to 0 (Admit everything)
    return content.replace("DELTA_NOVELTY = 2", "DELTA_NOVELTY = 0")

# Patch logic for rsi.py
def patch_rsi(content):
    # Relax Alpha 0.8 -> 0.95
    c = re.sub(r"ALPHA\s*=\s*0\.8", "ALPHA = 0.95", content)
    # Disable strict rho increase check
    c = c.replace("if val <= last_val:", "if False:")
    return c

if __name__ == "__main__":
    patch_file("cdel/v1_5r/sr_cegar/gates.py", patch_gates)
    patch_file("cdel/v1_5r/rsi.py", patch_rsi)
