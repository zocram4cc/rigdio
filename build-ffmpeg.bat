@echo off
echo Building minimal ffmpeg.exe for rigdio...
echo.
echo MSYS2 and required packages will be installed automatically if not present.
echo.
python build-ffmpeg.py --output ffmpeg.exe
echo.
pause
