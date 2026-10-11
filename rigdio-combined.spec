# -*- mode: python ; coding: utf-8 -*-

# Combined spec that builds both rigdio.exe and rigdj.exe into a single
# dist/rigdio/ directory with a shared _internal folder. This avoids
# duplicating the shared Python runtime / Tcl-Tk / dependencies.
#
# Build with: py -3.13 -m PyInstaller rigdio-combined.spec -y

rigdio_a = Analysis(
    ['rigdio.py'],
    pathex=[],
    binaries=[],
    datas=[('rigdio.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
rigdio_pyz = PYZ(rigdio_a.pure)

rigdj_a = Analysis(
    ['rigdj.py'],
    pathex=[],
    binaries=[],
    datas=[('rigdj.ico', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
rigdj_pyz = PYZ(rigdj_a.pure)

rigdio_exe = EXE(
    rigdio_pyz,
    rigdio_a.scripts,
    [],
    exclude_binaries=True,
    name='rigdio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['rigdio.ico'],
)

rigdj_exe = EXE(
    rigdj_pyz,
    rigdj_a.scripts,
    [],
    exclude_binaries=True,
    name='rigdj',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['rigdj.ico'],
)

coll = COLLECT(
    rigdio_exe,
    rigdio_a.binaries,
    rigdio_a.datas,
    rigdj_exe,
    rigdj_a.binaries,
    rigdj_a.datas,
    name='rigdio',
)
