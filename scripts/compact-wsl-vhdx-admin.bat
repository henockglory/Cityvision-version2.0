@echo off
set LOG=C:\Users\gheno\citevision\scripts\compact-admin-log.txt
echo [%date% %time%] Start > "%LOG%"

wsl --shutdown >> "%LOG%" 2>&1
timeout /t 8 /nobreak >> "%LOG%" 2>&1

for /f "delims=" %%F in ('powershell -NoProfile -Command "Get-ChildItem -LiteralPath 'C:\Users\gheno\AppData\Local\wsl' -Recurse -Filter ext4.vhdx -Force | Where-Object { -not ($_.Attributes -band [IO.FileAttributes]::SparseFile) } | Sort-Object Length -Descending | Select-Object -First 1 -ExpandProperty FullName"') do set VHDX=%%F

if not defined VHDX (
  echo Aucun ext4.vhdx WSL trouve >> "%LOG%"
  echo Aucun ext4.vhdx WSL trouve.
  exit /b 1
)

echo VHDX: %VHDX% >> "%LOG%"
echo Cible: %VHDX%
echo Before: >> "%LOG%"
dir "%VHDX%" >> "%LOG%" 2>&1

(
  echo select vdisk file="%VHDX%"
  echo attach vdisk readonly
  echo compact vdisk
  echo detach vdisk
  echo exit
) > "%TEMP%\cv-vhdx.txt"

echo Running diskpart... >> "%LOG%"
diskpart /s "%TEMP%\cv-vhdx.txt" >> "%LOG%" 2>&1
echo diskpart exit: %ERRORLEVEL% >> "%LOG%"

echo After: >> "%LOG%"
dir "%VHDX%" >> "%LOG%" 2>&1

wmic logicaldisk where "DeviceID='C:'" get FreeSpace,Size >> "%LOG%" 2>&1
echo Done >> "%LOG%"
echo Done. Voir %LOG%
