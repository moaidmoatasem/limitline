@echo off
rem Double-click to install Limitline for the current user (no admin needed).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
echo.
pause
