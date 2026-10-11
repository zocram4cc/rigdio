Rigdio (with RigDJ)
================
**Rigdio** is an automated goalhorn/anthem player designed to ease the burden on streamers during cup events, and increase the options available to managers/caretakers for the team's music exports.<br>
**RigDJ** is the GUI editor for .4ccm files, released along with Rigdio. It allows for graphical editing of anthem and player songs as well as the various conditions you can set for them. If you intend to use more complex instructions for your music, it is recommended you use RigDJ to avoid needing to know the .4ccm formatting for every condition type.

If you're just looking for the program, you can find it [here](https://github.com/the4chancup/rigdio/releases). Information on how to use Rigdio/RigDJ themselves can also be found [here](https://implyingrigged.info/wiki/Rigdio).

## Build Guide
If you're interested in building Rigdio/RigDJ yourself, here's some info that'll help.

### Requirements
* [Python 3.13](https://github.com/adang1345/PythonVista) - Programming language required to run and build the code. You must use the Windows 7-compatible Python 3.13 builds from PythonVista, not the official Python releases. The official Python 3.9+ releases dropped Windows 7 support, but PythonVista provides backported builds that work on Windows 7 while giving you access to modern Python features. Any 3.13.x version from PythonVista will do.
* [libmpv (64-bit)](https://github.com/eko5624/mpv-win64/releases/tag/2024-04-29) - The mpv media library DLL required to play songs on Rigdio. You must use a Windows 7-compatible build — recent mpv builds from the official source require Windows 8.1+ or 10+. Download `git-libmpv.7z` from the [last Win7-compatible release](https://github.com/eko5624/mpv-win64/releases/tag/2024-04-29) (April 2024, mpv v0.38.0), extract `libmpv-2.dll` from it, and place it in the project and release folders.
* [python-mpv](https://pypi.org/project/python-mpv/) - Python module used for utilising the mpv media library functions to play songs on Rigdio.
* [PyYAML](https://pypi.org/project/PyYAML/) - Python module used for parsing the default settings used in Rigdio.
* [pyinstaller](https://pypi.org/project/pyinstaller/) - Python module used for building the executable files.
* [UPX](https://github.com/upx/upx/releases) - Optional. Executable packer used to compress the `_internal` binaries after building, reducing total size by ~70%. Download the win64 zip, extract it to `tools/upx/`, and the build script will use it automatically.
* [ffmpeg](https://www.ffmpeg.org/download.html) - Multimedia framework required for loudness analysis. A minimal `ffmpeg.exe` (~1.8 MB) is included in the repository. If you need to rebuild it, see the instructions below.

### Running the Python file
If you've made any changes to the code and wish to test them out without having to build the whole program, you can run it directly through Command Prompt. Open up Command Prompt in your project folder and enter `python (name of code file)`. This also allows you to see whatever messages/errors Rigdio/RigDJ spits out while it's running, making it easier to debug.

For example, the command line to run Rigdio is
```
python rigdio.py
```

Similarly, the command line to run RigDJ is
```
python rigdj.py
```

### Building a Minimal ffmpeg.exe
Rigdio only uses ffmpeg for loudness analysis via the `volumedetect` filter. The full ffmpeg build is ~140 MB, but a minimal build with only the required components is ~1.8 MB. A build script is provided to automate this process.

Run the following batch file:
```
build-ffmpeg.bat
```

This will:
1. Download and install [MSYS2](https://www.msys2.org/) automatically if not already present.
2. Install the required MSYS2 packages (GCC, make, nasm, etc.) automatically.
3. Clone the ffmpeg source (tag n4.4.1, for Windows 7 compatibility).
4. Configure and build a minimal `ffmpeg.exe` with only the decoders, demuxers, parsers, filters, and protocols that Rigdio needs.
5. Copy the built `ffmpeg.exe` to the project folder.

**Notes:**
* On the first run with a fresh MSYS2 installation, the core system update may terminate the MSYS2 terminal. This is normal — just re-run `build-ffmpeg.bat` and it will continue from where it left off.
* The build uses `--disable-asm` to work around GCC 14 incompatibilities with ffmpeg n4.4.1's inline assembly. The performance impact is negligible for loudness analysis.
* The resulting `ffmpeg.exe` is statically linked and has no external DLL dependencies beyond standard Windows system libraries.
* You can pass `--jobs N` to control parallelism: `python build-ffmpeg.py --jobs 4`.

### Building Rigdio/RigDJ
Once you've fully made and tested out your code changes, you can start building the executables. Run **compile-combined.bat** to build both Rigdio and RigDJ into a single `dist/rigdio/` folder with a shared `_internal` directory containing the bundled Python runtime and dependencies. Both executables share the same `_internal` folder, avoiding duplication of the ~53 MB of common dependencies.<br>
**TIP:** Replace the contents of the Rigdio release folder with your own built ones before testing it out to have a more accurate runtime environment.

If UPX is installed in `tools/upx/`, the build will also compress the binaries in `_internal` to reduce the total size by ~70%. UPX is optional — the build works without it, just with larger output.

If you're on Mac/Linux then you will need to run the command line manually. The build uses a spec file:
```
pyinstaller rigdio-combined.spec -y
```
Then optionally compress the binaries:
```
python compress-internal.py
```

### Assembling a Release
To create a complete Rigdio release package, you will need the following files in a single folder:
* `rigdio.exe`, `rigdj.exe`, and their shared `_internal` folder - Built from `compile-combined.bat`
* `libmpv-2.dll` - The 64-bit mpv library DLL (place inside `_internal/`)
* `ffmpeg.exe` - Minimal ffmpeg build (included in the repo, or rebuild with `build-ffmpeg.bat`; place inside `_internal/`)
* `changelog.txt` - Changelog file (included in the repo)

The `compile-combined.bat` script copies `libmpv-2.dll`, `ffmpeg.exe`, and `changelog.txt` into the build output automatically. `config.yml` is not included — rigdio generates it on first run.
