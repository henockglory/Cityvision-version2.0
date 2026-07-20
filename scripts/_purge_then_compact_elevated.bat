@echo off
:: Double-clic / Run as Administrator — purge preuves WSL puis compact C:
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_purge_then_compact_elevated.ps1"
pause
