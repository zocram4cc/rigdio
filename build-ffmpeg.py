#!/usr/bin/env python3
"""
Build a minimal ffmpeg.exe for rigdio's loudness analysis.

Rigdio uses two ffmpeg invocations:
  1. ffmpeg -i <file> -af volumedetect -f null -        (all songs: mean/peak)
  2. ffmpeg -i <file> -f s16le -ar 8000 -ac 1 -         (chants only: loud-part RMS)
So we need a handful of decoders, the volumedetect and aresample filters,
file+pipe protocols, and null+s16le muxers. This produces an ffmpeg.exe
around 10-20 MB instead of the full ~140 MB.

This script automatically installs MSYS2 and all required packages if
they are not already present.

Usage:
  python build-ffmpeg.py [--output ffmpeg.exe] [--jobs N]

Options:
  --output PATH   Destination for the built ffmpeg.exe (default: ./ffmpeg.exe)
  --jobs N        Number of parallel build jobs (default: CPU count)
  --msys2 PATH    Path to MSYS2 installation (default: auto-detect/install)
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

FFMPEG_REPO = "https://git.ffmpeg.org/ffmpeg.git"
FFMPEG_TAG = "n4.4.1"
MSYS2_INSTALLER = "https://github.com/msys2/msys2-installer/releases/download/2024-12-08/msys2-x86_64-20241208.exe"

# Minimal set of decoders for common audio formats in 4cc exports
DECODERS = [
    "mp3", "mp3float",
    "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le",
    "pcm_u8", "pcm_s8",
    "flac",
    "vorbis",
    "aac",
    "opus",
    "alac",
    "wmav2",
    "adpcm_ima_wav", "adpcm_ms",
]

# Demuxers for the container formats we need
DEMUXERS = [
    "mp3", "wav", "ogg", "flac", "mov", "matroska", "avi", "asf",
    "aac", "dsf",
]

# Parsers needed by the decoders
PARSERS = [
    "mpegaudio", "aac", "ac3", "flac", "opus", "vorbis",
]

# Filters: volumedetect for loudness analysis, aresample for PCM resampling
FILTERS = [
    "volumedetect", "anull", "aresample",
]

# File protocol for input, pipe protocol for PCM output to stdout
PROTOCOLS = [
    "file",
    "pipe",
]

# Muxers: null for volumedetect output, pcm_s16le for raw PCM output (chant loud-part analysis)
# Note: the configure name is pcm_s16le (maps to CONFIG_PCM_S16LE_MUXER), though ffmpeg -formats
# displays it as "s16le". The -f s16le flag at runtime uses the display name.
MUXERS = [
    "null",
    "pcm_s16le",
]

# Encoders needed (pcm_s16le is required by the null muxer)
ENCODERS = [
    "pcm_s16le",
]

# MSYS2 packages required for building ffmpeg
PACMAN_PACKAGES = [
    "mingw-w64-x86_64-make",
    "mingw-w64-x86_64-gcc",
    "git",
    "mingw-w64-x86_64-nasm",
    "mingw-w64-x86_64-yasm",
    "mingw-w64-x86_64-pkg-config",
    "mingw-w64-x86_64-dlfcn",
    "diffutils",
]

def run(cmd, cwd=None, env=None, check=True, shell=False):
    print(">> " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, env=env, shell=shell, stdout=None, stderr=subprocess.STDOUT)
    if check and result.returncode != 0:
        print("ERROR: command failed with exit code {}".format(result.returncode))
        sys.exit(1)
    return result

def find_msys2(explicit_path=None):
    if explicit_path:
        if os.path.isdir(explicit_path):
            return explicit_path
        return None
    # Common MSYS2 install locations
    candidates = [
        r"C:\msys64",
        r"C:\msys2",
        os.path.expanduser(r"~\msys64"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None

def install_msys2():
    """Download and silently install MSYS2 to C:\\msys64."""
    print("\n=== MSYS2 not found, installing automatically ===")
    install_dir = r"C:\msys64"

    # Download the installer
    print("Downloading MSYS2 installer...")
    installer_path = os.path.join(tempfile.gettempdir(), "msys2-installer.exe")
    urllib.request.urlretrieve(MSYS2_INSTALLER, installer_path)
    print("Downloaded to: {}".format(installer_path))

    # Run silent install
    print("Installing MSYS2 to {} (this may take a few minutes)...".format(install_dir))
    run([installer_path, "install", "--root", install_dir, "--confirm-command"])

    # Clean up installer
    try:
        os.remove(installer_path)
    except OSError:
        pass

    if not os.path.isdir(install_dir):
        print("ERROR: MSYS2 installation appears to have failed.")
        sys.exit(1)

    print("MSYS2 installed successfully.")
    return install_dir

def run_msys_command(msys2, command, env=None, check=True):
    """Run a command inside the MSYS2 bash environment with streamed output."""
    bash = os.path.join(msys2, "usr", "bin", "bash.exe")
    cmd = [bash, "--login", "-c", command]
    print(">> " + " ".join(cmd))
    result = subprocess.run(cmd, env=env, stdout=None, stderr=subprocess.STDOUT)
    if check and result.returncode != 0:
        print("ERROR: command failed with exit code {}".format(result.returncode))
        sys.exit(1)
    return result

def ensure_pacman_packages(msys2):
    """Ensure all required pacman packages are installed."""
    print("\n=== Checking MSYS2 packages ===")

    bash = os.path.join(msys2, "usr", "bin", "bash.exe")

    # Run core system update. On a fresh install this may kill all MSYS2
    # processes (including our bash) as it updates core packages. It may
    # also fail due to network issues. Either way, the user re-runs the
    # script and we try again. If already up to date, it completes instantly.
    print("Updating MSYS2 core system...")
    for attempt in range(3):
        result = subprocess.run(
            [bash, "--login", "-c", "pacman --noconfirm -Syu"],
        )
        if result.returncode == 0:
            print("Core system update complete.")
            break
        print("Core update attempt {} failed (exit code {}).".format(
            attempt + 1, result.returncode))
        if attempt < 2:
            print("Retrying in 5 seconds...")
            import time
            time.sleep(5)
        else:
            print("Core update failed after 3 attempts.")
            print("This may be a network issue. Please re-run build-ffmpeg.bat.")
            print("If MSYS2 terminals were closed during the update, that is normal")
            print("on a fresh install — just re-run the script.")
            sys.exit(1)

    # Check which packages are already installed
    result = subprocess.run(
        [bash, "--login", "-c", "pacman -Q --quiet"],
        capture_output=True, text=True
    )
    installed = set(result.stdout.strip().split("\n")) if result.stdout else set()

    # Some mingw packages may show as different names (e.g. pkg-config vs pkgconf)
    needed = []
    for pkg in PACMAN_PACKAGES:
        if pkg not in installed:
            if pkg == "mingw-w64-x86_64-pkg-config" and "mingw-w64-x86_64-pkgconf" in installed:
                continue
            needed.append(pkg)

    if needed:
        print("Installing missing packages: {}".format(", ".join(needed)))
        pkg_str = " ".join(needed)
        run_msys_command(msys2, "pacman --noconfirm -S {}".format(pkg_str))
    else:
        print("All required packages already installed.")

def main():
    parser = argparse.ArgumentParser(description="Build minimal ffmpeg.exe for rigdio")
    parser.add_argument("--output", default="ffmpeg.exe", help="Output path for ffmpeg.exe")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel build jobs")
    parser.add_argument("--msys2", default=None, help="Path to MSYS2 installation")
    args = parser.parse_args()

    # 1. Find or install MSYS2
    msys2 = find_msys2(args.msys2)
    if not msys2:
        msys2 = install_msys2()

    print("Using MSYS2 at: {}".format(msys2))

    # 2. Ensure required packages are installed
    ensure_pacman_packages(msys2)

    # 3. Set up build environment with MSYS2 paths
    mingw_bin = os.path.join(msys2, "mingw64", "bin")
    msys_bin = os.path.join(msys2, "usr", "bin")

    env = os.environ.copy()
    env["PATH"] = mingw_bin + os.pathsep + msys_bin + os.pathsep + env.get("PATH", "")
    env["MSYSTEM"] = "MINGW64"

    # 4. Clone or update ffmpeg source
    work_dir = os.path.abspath("ffmpeg-build")
    src_dir = os.path.join(work_dir, "ffmpeg")

    if not os.path.isdir(src_dir):
        os.makedirs(work_dir, exist_ok=True)
        run(["git", "clone", "--branch", FFMPEG_TAG, "--depth", "1", FFMPEG_REPO, src_dir], cwd=work_dir)
    else:
        print("ffmpeg source already exists, using existing checkout")

    # 5. Build configure arguments
    configure = [
        "./configure",
        "--disable-everything",
        "--enable-ffmpeg",
        "--disable-ffprobe",
        "--disable-ffplay",
        "--disable-doc",
        "--disable-avdevice",
        "--disable-postproc",
        "--disable-network",
        "--disable-autodetect",
        "--disable-asm",
        "--enable-small",
        "--enable-avcodec",
        "--enable-avformat",
        "--enable-avutil",
        "--enable-swresample",
        "--enable-w32threads",
        "--extra-cflags=-Os",
        "--extra-ldflags='-s -static'",
        "--extra-libs=-lwinpthread",
    ]

    for d in DECODERS:
        configure.append("--enable-decoder=" + d)
    for d in DEMUXERS:
        configure.append("--enable-demuxer=" + d)
    for p in PARSERS:
        configure.append("--enable-parser=" + p)
    for f in FILTERS:
        configure.append("--enable-filter=" + f)
    for p in PROTOCOLS:
        configure.append("--enable-protocol=" + p)
    for m in MUXERS:
        configure.append("--enable-muxer=" + m)
    for e in ENCODERS:
        configure.append("--enable-encoder=" + e)

    # 6. Run configure (via MSYS2 bash so ./configure works)
    # Run make distclean first to remove stale object files from previous builds,
    # so that changed configure flags (e.g. new muxers) are properly picked up.
    print("\n=== Configuring ffmpeg ===")
    run_msys_command(msys2, "cd '{}' && mingw32-make distclean || true".format(
        src_dir.replace("\\", "/")), env=env, check=False)
    configure_cmd = " ".join(configure)
    run_msys_command(msys2, "cd '{}' && {}".format(src_dir.replace("\\", "/"), configure_cmd), env=env)

    # 7. Build
    print("\n=== Building ffmpeg ===")
    run_msys_command(msys2, "cd '{}' && mingw32-make -j{}".format(
        src_dir.replace("\\", "/"), args.jobs), env=env)

    # 8. Copy output
    built_exe = os.path.join(src_dir, "ffmpeg.exe")
    output_path = os.path.abspath(args.output)
    if not os.path.isfile(built_exe):
        print("ERROR: ffmpeg.exe was not built")
        sys.exit(1)

    shutil.copy2(built_exe, output_path)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print("\n=== Done! ===")
    print("Built: {} ({:.1f} MB)".format(output_path, size_mb))
    print("Compare to full ffmpeg.exe (~140 MB)")

if __name__ == "__main__":
    main()
