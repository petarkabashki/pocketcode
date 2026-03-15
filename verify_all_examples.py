import os
import subprocess
from pathlib import Path

EXAMPLES_DIR = Path("examples")

def find_stackvm_scripts():
    scripts = []
    for root, _, files in os.walk(EXAMPLES_DIR):
        for file in files:
            if file.endswith((".md", ".vm")):
                # Check if it has a vm block or front matter indicative of a script
                filepath = Path(root) / file
                try:
                    content = filepath.read_text()
                    if "```vm" in content or "vm_entry:" in content:
                        scripts.append(filepath)
                except Exception:
                    pass
    return scripts

def run_script(script_path):
    print(f"Testing: {script_path}")
    cmd = [
        ".venv/bin/python3",
        "-m", "pocketcode.main",
        "--prompt", f"/stackvm check script {script_path}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {script_path}")
        print(result.stderr)
        return False
    return True

if __name__ == "__main__":
    scripts = find_stackvm_scripts()
    print(f"Found {len(scripts)} StackVM scripts.")
    failed = []
    
    # We will use /stackvm check instead of run to avoid side effects and prompts,
    # but still verify that compilation and static analysis don't crash the engine.
    for script in scripts:
        if not run_script(script):
            failed.append(script)

    if failed:
        print(f"\nFailed scripts ({len(failed)}):")
        for f in failed:
            print(f"  {f}")
    else:
        print("\nAll scripts successfully checked!")
