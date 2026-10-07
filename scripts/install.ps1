# Installs Limitline for the current Windows user.
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Uninstall
param([switch]$Uninstall)
$ErrorActionPreference = "Stop"
$dest  = Join-Path $env:LOCALAPPDATA "Limitline"
$menu  = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$link  = Join-Path $menu "Limitline.lnk"

if ($Uninstall) {
  Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
  Remove-Item -Force $link -ErrorAction SilentlyContinue
  Write-Host "Removed. Settings file ~\.limitline.json was kept."
  exit 0
}

# Prefer pythonw so no console window stays open
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
  $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
  if ($py) { $pyw = Join-Path (Split-Path $py) "pythonw.exe" }
}
if (-not $pyw -or -not (Test-Path $pyw)) {
  Write-Host "Python 3.8+ (with tkinter) is required: https://www.python.org/downloads/"
  exit 1
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null
$src = Join-Path (Split-Path $PSScriptRoot) "limitline.py"
Copy-Item $src (Join-Path $dest "limitline.py") -Force

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $pyw
$sc.Arguments  = '"' + (Join-Path $dest "limitline.py") + '"'
$sc.WorkingDirectory = $dest
$sc.Description = "Floating monitor for Claude Code usage"
$sc.Save()

Write-Host "Installed to $dest"
Write-Host "Start it from the Start menu: 'Limitline'."
Write-Host "Start at login: open the app > Settings (S) > Launch at login."
