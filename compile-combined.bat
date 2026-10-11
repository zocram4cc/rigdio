@echo off
REM Build both rigdio.exe and rigdj.exe into a single dist/rigdio/ folder
REM with a shared _internal directory.
REM UPX is optional — if found in tools\upx\, binaries are compressed;
REM otherwise the build proceeds uncompressed.
if exist "%~dp0tools\upx\upx-5.2.0-win64\upx.exe" (
    echo UPX found, binaries will be compressed after build.
) else (
    echo UPX not found, binaries will be uncompressed.
)
py -3.13 -m PyInstaller rigdio-combined.spec -y
if errorlevel 1 exit /b 1
py -3.13 compress-internal.py
REM Copy required runtime dependencies from the project root
if not exist "%~dp0libmpv-2.dll" (
    echo.
    echo *** WARNING: libmpv-2.dll not found in project root! ***
    echo *** rigdio will not be able to play audio without it. ***
    echo *** Download it from https://github.com/eko5624/mpv-win64/releases/tag/2024-04-29 ***
    echo.
) else (
    copy /Y "%~dp0libmpv-2.dll" "%~dp0dist\rigdio\_internal\"
)
if not exist "%~dp0ffmpeg.exe" (
    echo.
    echo *** WARNING: ffmpeg.exe not found in project root! ***
    echo *** rigdio will not be able to normalize volume without it. ***
    echo *** See the build guide for instructions on building a minimal ffmpeg.exe. ***
    echo.
) else (
    copy /Y "%~dp0ffmpeg.exe" "%~dp0dist\rigdio\_internal\"
)
if exist "%~dp0changelog.txt" copy /Y "%~dp0changelog.txt" "%~dp0dist\rigdio\"

pause
