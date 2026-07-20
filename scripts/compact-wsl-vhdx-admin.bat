@echo off
setlocal
set LOG=C:\Users\gheno\citevision\scripts\compact-admin-log.txt
echo [%date% %time%] Start compact sequence >> "%LOG%"

echo === WSL shutdown ===
wsl --shutdown >> "%LOG%" 2>&1
timeout /t 20 /nobreak >> "%LOG%" 2>&1

echo === set-sparse false ===
wsl --manage Ubuntu-24.04 --set-sparse false >> "%LOG%" 2>&1

for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem -LiteralPath 'C:\Users\gheno\AppData\Local\wsl' -Recurse -Filter ext4.vhdx -Force -ErrorAction SilentlyContinue | Sort-Object Length -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set VHDX=%%F

if not defined VHDX (
  echo Aucun ext4.vhdx trouve >> "%LOG%"
  exit /b 1
)

echo VHDX=%VHDX% >> "%LOG%"
echo Cible: %VHDX%
dir "%VHDX%" >> "%LOG%" 2>&1

(
  echo select vdisk file="%VHDX%"
  echo attach vdisk readonly
  echo compact vdisk
  echo detach vdisk
  echo exit
) > "%TEMP%\cv-vhdx-compact.txt"

echo === diskpart compact ===
diskpart /s "%TEMP%\cv-vhdx-compact.txt" >> "%LOG%" 2>&1
echo diskpart exit: %ERRORLEVEL% >> "%LOG%"

dir "%VHDX%" >> "%LOG%" 2>&1

echo === set-sparse true ===
wsl --manage Ubuntu-24.04 --set-sparse true >> "%LOG%" 2>&1

powershell -NoProfile -File "C:\Users\gheno\citevision\scripts\_vhdx_sizes.ps1" >> "%LOG%" 2>&1
echo Done. Log: %LOG%
