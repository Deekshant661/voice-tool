# Starts Voice Tool at login (no console window) via a shortcut in the Startup folder.
param([string]$StartupDir = [Environment]::GetFolderPath("Startup"))
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $env:USERPROFILE ".voice-tool\venv\Scripts\pythonw.exe"

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $StartupDir "Voice Tool.lnk"))
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "-m voicetool"
$shortcut.WorkingDirectory = $repo
$shortcut.Description = "Voice Tool - hold Right Ctrl to dictate"
$shortcut.Save()
Write-Host "Voice Tool will start at login."
