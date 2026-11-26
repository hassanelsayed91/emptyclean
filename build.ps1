param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$icon = Join-Path $PSScriptRoot "assets\emptyclean.ico"
if (-not (Test-Path $icon)) { throw "Icon not found: $icon" }
if (-not $SkipInstall) { python -m pip install --upgrade pyinstaller }
function Invoke-PyInstaller { param([string[]]$ArgList); & python -m PyInstaller @ArgList; if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" } }
Invoke-PyInstaller @("--noconfirm","--clean","--onefile","--windowed","--name","EmptyClean","--icon",$icon,"--distpath","dist\gui","--workpath","build\gui","--specpath","build","run_gui.py")
Invoke-PyInstaller @("--noconfirm","--clean","--onefile","--console","--name","EmptyClean-CLI","--icon",$icon,"--distpath","dist\cli","--workpath","build\cli","--specpath","build","run_cli.py")
Copy-Item "dist\gui\EmptyClean.exe" "dist\EmptyClean.exe" -Force
Copy-Item "dist\cli\EmptyClean-CLI.exe" "dist\EmptyClean-CLI.exe" -Force
Remove-Item -Recurse -Force "dist\gui","dist\cli"
Write-Host "Done" -ForegroundColor Green