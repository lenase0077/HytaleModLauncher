$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

& $python -m PyInstaller `
  --noconfirm `
  --windowed `
  --onefile `
  --name HytaleModLauncher `
  --clean `
  hytale_launcher\main.py

Write-Host "EXE generado en dist\HytaleModLauncher.exe"
