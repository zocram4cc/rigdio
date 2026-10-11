"""Post-build UPX compression for PyInstaller onedir _internal folder.

Compresses all .exe, .dll, and .pyd files in the _internal directory
using UPX. Skips files that are already compressed. UPX is optional —
if not found, this script exits silently.
"""
import os
import shutil
import subprocess

# UPX path: look in tools/upx/ relative to the project root, or on PATH
def find_upx():
    # Check tools/upx/ subdirectories
    here = os.path.dirname(os.path.abspath(__file__))
    tools_upx = os.path.join(here, "tools", "upx")
    if os.path.isdir(tools_upx):
        for root, dirs, files in os.walk(tools_upx):
            if "upx.exe" in files:
                return os.path.join(root, "upx.exe")
    # Check PATH
    return shutil.which("upx")


def main():
    upx = find_upx()
    if not upx:
        print("UPX not found, skipping compression.")
        return

    internal = os.path.join(here, "dist", "rigdio", "_internal")
    if not os.path.isdir(internal):
        print("_internal folder not found at", internal)
        return

    extensions = (".exe", ".dll", ".pyd")
    targets = []
    for root, dirs, files in os.walk(internal):
        for f in files:
            if f.lower().endswith(extensions):
                targets.append(os.path.join(root, f))

    if not targets:
        print("No compressible files found.")
        return

    before = sum(os.path.getsize(t) for t in targets)
    print(f"Compressing {len(targets)} files with UPX ({upx})...")
    print(f"Size before: {before / 1048576:.1f} MB")

    # Run UPX on all targets at once with best compression
    result = subprocess.run(
        [upx, "--best", "--lzma", "-q"] + targets,
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # UPX returns non-zero if some files are already compressed or unsupported
        # Print warnings but don't fail the build
        for line in result.stderr.strip().splitlines():
            if line and "AlreadyPackedException" not in line and "CantPackException" not in line:
                print(f"UPX warning: {line}")

    after = sum(os.path.getsize(t) for t in targets)
    saved = before - after
    ratio = (saved / before * 100) if before > 0 else 0
    print(f"Size after:  {after / 1048576:.1f} MB")
    print(f"Saved:       {saved / 1048576:.1f} MB ({ratio:.0f}%)")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    main()
