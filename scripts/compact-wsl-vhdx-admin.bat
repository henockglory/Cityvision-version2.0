@echo off
set LOG=C:\Users\gheno\citevision\scripts\compact-admin-log.txt
echo [%date% %time%] Start > "%LOG%"

wsl --shutdown >> "%LOG%" 2>&1
timeout /t 8 /nobreak >> "%LOG%" 2>&1

set VHDX=C:\Users\gheno\AppData\Local\wsl\{0fa6a1b8-39ef-4ca2-ae78-f6eabf8bb04d}\ext4.vhdx
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
