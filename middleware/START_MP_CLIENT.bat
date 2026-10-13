@echo off
REM CLIENT launcher for the multiplayer beta. Run on every CLIENT machine.
REM Edit the three values below, then double-click.
set HOSTIP=192.168.1.50
set PASSWORD=change-me-before-hosting
set PLAYERNAME=Player1
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found on PATH. Install Python 3.10+ from python.org with tcl/tk. & pause & exit /b 1)
python mp_agent.py --host %HOSTIP% --password %PASSWORD% --player %PLAYERNAME%
pause
