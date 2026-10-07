# Limitline installer for Windows (current user, no admin needed).
#   Double-click install.bat   or   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#   One-liner (after publishing):  irm https://raw.githubusercontent.com/<you>/limitline/main/scripts/install.ps1 | iex
# Options: -Uninstall  -NoAutostart  -NoLaunch  -Desktop
param([switch]$Uninstall, [switch]$NoAutostart, [switch]$NoLaunch, [switch]$Desktop,
      [string]$Repo = "moaidmoatasem/limitline")
$ErrorActionPreference = "Stop"
$dest = Join-Path $env:LOCALAPPDATA "Limitline"
$menu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$link = Join-Path $menu "Limitline.lnk"
$dlink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Limitline.lnk"

function Find-Python {
  foreach ($n in @("pythonw.exe", "python.exe")) {
    $c = Get-Command $n -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notlike "*WindowsApps*") { return (Split-Path $c.Source) }
  }
  foreach ($d in Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending) {
    if (Test-Path (Join-Path $d.FullName "pythonw.exe")) { return $d.FullName }
  }
  return $null
}

if ($Uninstall) {
  $py = Find-Python
  if ($py -and (Test-Path "$dest\limitline.py")) {
    & (Join-Path $py "python.exe") "$dest\limitline.py" --uninstall-statusline 2>$null
    & (Join-Path $py "python.exe") "$dest\limitline.py" --autostart off 2>$null
  }
  Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
  Remove-Item -Force $link, $dlink -ErrorAction SilentlyContinue
  Write-Host "Removed Limitline, its Start-menu shortcut, startup entry and status-line hook. Your settings file (~\.limitline.json) was kept."
  exit 0
}

# 1. Python (with tkinter)
$pyDir = Find-Python
if (-not $pyDir) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Python not found. Installing Python 3.12 with winget (about 1 minute)..."
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $pyDir = Find-Python
  }
}
if (-not $pyDir) {
  Write-Host "Python 3.8+ is needed. Install it from https://www.python.org/downloads/ (keep 'tcl/tk' ticked) and run this again."
  exit 1
}
$python = Join-Path $pyDir "python.exe"
$pythonw = Join-Path $pyDir "pythonw.exe"
& $python -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "This Python has no tkinter. Re-run the Python installer, choose Modify, and tick 'tcl/tk and IDLE'."
  exit 1
}

# 2. Copy the app (from this folder, or download it when run as a one-liner)
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$target = Join-Path $dest "limitline.py"
$local = if ($PSScriptRoot) { Join-Path (Split-Path $PSScriptRoot) "limitline.py" } else { "" }
if ($local -and (Test-Path $local)) { Copy-Item $local $target -Force }
else {
  Write-Host "Downloading Limitline..."
  Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/$Repo/main/limitline.py" -OutFile $target
}

# 3. Shortcuts
$shell = New-Object -ComObject WScript.Shell
foreach ($p in @($link) + $(if ($Desktop) { @($dlink) } else { @() })) {
  $sc = $shell.CreateShortcut($p)
  $sc.TargetPath = $pythonw
  $sc.Arguments = '"' + $target + '"'
  $sc.WorkingDirectory = $dest
  $sc.Description = "Floating monitor for Claude Code usage (unofficial)"
  $sc.Save()
}

# 4. Optional one-time setup (the app also offers these in its welcome window)
& $python $target --install-statusline
if (-not $NoAutostart) { & $python $target --autostart on }

Write-Host ""
Write-Host "Installed. Start menu > Limitline. Run '$python $target --selftest' to check this computer."
if (-not $NoLaunch) { Start-Process $pythonw -ArgumentList ('"' + $target + '"') }
