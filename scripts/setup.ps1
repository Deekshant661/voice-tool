# Creates the Python environment for Voice Tool outside OneDrive and installs dependencies.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
# Not %LOCALAPPDATA%: packaged apps (like the Claude desktop app) get AppData redirected into a
# private sandbox, so files written from there are invisible to anything launched normally.
$appDir = Join-Path $env:USERPROFILE ".voice-tool"
$venv = Join-Path $appDir "venv"
$models = Join-Path $appDir "models"
$repo = Split-Path -Parent $PSScriptRoot

New-Item -ItemType Directory -Force $appDir | Out-Null

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r (Join-Path $repo "requirements.txt")
& $py -m pip cache purge | Out-Null

# Reuse the model downloaded during the speed test instead of downloading it again.
if ((Test-Path "C:\wspike") -and -not (Test-Path $models)) {
    Move-Item "C:\wspike" $models
}

Write-Host "Python: $py"
