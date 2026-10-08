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

function Invoke-Exe {
  # Runs a native command, silences its stderr, forwards its stdout, and returns only the exit
  # code - without $ErrorActionPreference="Stop" turning PowerShell 5.1's redirected-stderr
  # NativeCommandError into a script-killing error. Full stdout is left in $script:LastExeOut.
  param([string]$Exe, [string[]]$Arguments)
  $eap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $out = if ($Arguments) { & $Exe @Arguments 2>$null } else { & $Exe 2>$null }
    $script:LastExeOut = if ($out) { ($out | Out-String).Trim() } else { "" }
    if ($out) { foreach ($line in $out) { Write-Host $line } }
    return $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $eap
  }
}

if ($Uninstall) {
  $py = Find-Python
  $hook = 1
  if ($py -and (Test-Path "$dest\limitline.py")) {
    $hook = Invoke-Exe (Join-Path $py "python.exe") @("$dest\limitline.py", "--uninstall-statusline")
    if ($script:LastExeOut -like "*Nothing to restore*") { $hook = 0 }   # never connected: nothing of ours can dangle
    $null = Invoke-Exe (Join-Path $py "python.exe") @("$dest\limitline.py", "--autostart", "off")
  }
  Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
  Remove-Item -Force $link, $dlink -ErrorAction SilentlyContinue
  if ($hook -eq 0) {
    Write-Host "Removed Limitline, its Start-menu shortcut, startup entry and status-line hook. Your settings file (~\.limitline.json) was kept."
  } else {
    Write-Host "Removed Limitline, its Start-menu shortcut and startup entry. Your settings file (~\.limitline.json) was kept."
    Write-Host "Warning: Claude Code's status-line hook may still point at the removed file. If Claude Code shows a status-line error, delete the statusLine entry from ~\.claude\settings.json."
  }
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
if ((Invoke-Exe $python @("-c", "import tkinter")) -ne 0) {
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

# 2b. Application icon (the app also keeps this fresh in the accent colour on each launch)
$icon = Join-Path $dest "limitline.ico"
$null = Invoke-Exe $python @($target, "--write-icon", $icon)

# 3. Shortcuts
$shell = New-Object -ComObject WScript.Shell
foreach ($p in @($link) + $(if ($Desktop) { @($dlink) } else { @() })) {
  $sc = $shell.CreateShortcut($p)
  $sc.TargetPath = $pythonw
  $sc.Arguments = '"' + $target + '"'
  $sc.WorkingDirectory = $dest
  $sc.Description = "Floating monitor for Claude Code usage (unofficial)"
  if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
  $sc.Save()
}

# 4. Optional one-time setup (the app also offers these in its welcome window)
& $python $target --install-statusline
if (-not $NoAutostart) { & $python $target --autostart on }

Write-Host ""
Write-Host "Installed. Start menu > Limitline. Run '$python $target --selftest' to check this computer."
if (-not $NoLaunch) { Start-Process $pythonw -ArgumentList ('"' + $target + '"') }
