@echo off
echo === Shutdown WSL ===
wsl --shutdown
timeout /t 5 /nobreak >nul

echo === Enable sparse VHD (auto-reclaim on shutdown) ===
wsl --manage Ubuntu-24.04 --set-sparse true --allow-unsafe
wsl --manage Ubuntu --set-sparse true --allow-unsafe

echo === Start then shutdown to trigger compaction ===
wsl echo WSL started for sparse compaction
timeout /t 2 /nobreak >nul
wsl --shutdown
timeout /t 15 /nobreak >nul

echo === Disk check ===
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\gheno\citevision\scripts\_check-disk.ps1"
