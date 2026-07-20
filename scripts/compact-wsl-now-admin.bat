@echo off
REM Run as Administrator AFTER evidence purge — reclaim ~200 GB on C:.
REM Prerequisites: purge done + fstrim already run inside WSL.
echo.
echo === Compact WSL VHDX (needs Admin) ===
echo C: free BEFORE:
powershell -NoProfile -Command "(Get-PSDrive C).Free/1GB"
echo.
echo VHDX size BEFORE:
dir /s "C:\Users\gheno\AppData\Local\wsl\*\ext4.vhdx" 2>nul
echo.
echo Shutting down WSL (all terminals will stop)...
wsl --shutdown
timeout /t 20 /nobreak >nul
wsl --manage Ubuntu-24.04 --set-sparse false
echo Compacting ext4.vhdx (plusieurs minutes)...
diskpart /s "%~dp0diskpart-purge-compact.txt"
wsl --manage Ubuntu-24.04 --set-sparse true
echo.
echo C: free AFTER:
powershell -NoProfile -Command "(Get-PSDrive C).Free/1GB"
echo VHDX size AFTER:
dir /s "C:\Users\gheno\AppData\Local\wsl\*\ext4.vhdx" 2>nul
echo.
echo Done. Relance WSL puis dockerd si besoin.
