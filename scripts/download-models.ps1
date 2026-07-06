# Download optional AI models (InsightFace, YOLO) - offline, no fake data
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$modelsDir = Join-Path $Root 'ai-engine\models'
if (-not (Test-Path $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }

Write-Host "=== citevision Model Download ==="
Write-Host "[INFO] YOLOv8n ONNX - place at ai-engine/models/yolov8n.onnx"
Write-Host "[INFO] Download from: https://github.com/ultralytics/assets/releases (yolov8n.onnx)"
Write-Host "[INFO] InsightFace - set INSIGHTFACE_MODEL_PATH in .env when ready"
Write-Host "[INFO] PaddleOCR - set PADDLEOCR_MODEL_DIR in .env when ready"

$yolo = Join-Path $modelsDir 'yolov8n.onnx'
if (Test-Path $yolo) {
    Write-Host "[PASS] YOLO model present"
} else {
    Write-Host "[WARN] YOLO model missing - AI returns empty detections (no fake data)"
}

Write-Host "=== Secondary models (driver phone, seatbelt) ==="
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'download-secondary-models.ps1')
