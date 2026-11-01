# Stops Voice Tool from starting at login.
param([string]$StartupDir = [Environment]::GetFolderPath("Startup"))
$lnk = Join-Path $StartupDir "Voice Tool.lnk"
if (Test-Path $lnk) { Remove-Item $lnk }
Write-Host "Voice Tool will no longer start at login."
