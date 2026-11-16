@echo off
cd /d "%~dp0"
if exist "python\pythonw.exe" (
    start "" "python\pythonw.exe" "launcher.py"
    exit /b 0
)
if exist "python\python.exe" (
    start "" "python\python.exe" "launcher.py"
    exit /b 0
)
echo MS_helper: Python not found in python\ folder.
echo Put portable Python into the python\ folder and run again.
pause
