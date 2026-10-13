@echo off
REM HOST launcher for the multiplayer beta. Run ON THE HOST MACHINE ONLY.
REM Starts the normal middleware with the MP arbiter attached (port 8710).
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found on PATH. Install Python 3.10+ from python.org with tcl/tk. & pause & exit /b 1)
python mp_main.py
pause
