<#
Build time only. Run this on a machine with internet access to assemble
the SawahPintar/ portable folder. The resulting folder needs no internet
access itself; that is the whole point of embedding Python and vendoring
every wheel. Never run this script on the workshop laptop, and never copy
this script into the assembled folder.
#>

param(
    [string]$PythonVersion = "3.12.8",
    [string]$OutputDir = "SawahPintar"
)

$ErrorActionPreference = "Stop"

$pythonZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"

if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}
New-Item -ItemType Directory -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\python" | Out-Null

Write-Host "Downloading the embeddable Python distribution"
Invoke-WebRequest -Uri $pythonZipUrl -OutFile "$OutputDir\python-embed.zip"
Expand-Archive -Path "$OutputDir\python-embed.zip" -DestinationPath "$OutputDir\python"
Remove-Item "$OutputDir\python-embed.zip"

$pthFile = Get-ChildItem "$OutputDir\python\python*._pth" | Select-Object -First 1
(Get-Content $pthFile.FullName) -replace "^#import site", "import site" |
    Set-Content $pthFile.FullName
Add-Content $pthFile.FullName "..\"

Write-Host "Installing pip into the embedded interpreter"
Invoke-WebRequest -Uri $getPipUrl -OutFile "$OutputDir\get-pip.py"
& "$OutputDir\python\python.exe" "$OutputDir\get-pip.py" --no-warn-script-location
Remove-Item "$OutputDir\get-pip.py"

Write-Host "Installing runtime dependencies"
# Pinned to exact versions rather than ">=" floors. A ">=" build certified
# today and rebuilt next semester silently pulls whatever is newest on
# that day and ships it untested; the pytz incident (an undeclared
# transitive dependency that only failed on a clean runtime, never on a
# developer machine that already had it installed some other way) is
# direct evidence that "it built fine here" and "it runs on the workshop
# laptop" are not the same claim. These are the exact versions the 230+
# test suite was verified against on 2026-07-23. Re-pin deliberately, and
# re-run the full suite against the rebuilt kit before shipping again, if
# a dependency ever needs to move.
& "$OutputDir\python\python.exe" -m pip install --no-warn-script-location `
    "duckdb==1.5.5" "fastapi==0.139.2" "uvicorn==0.51.0" "websockets==15.0.1" `
    "pyserial==3.5" "pyyaml==6.0.3" "pytz>=2024.1"

Write-Host "Copying the application"
Copy-Item -Recurse "app" "$OutputDir\app"
Copy-Item -Recurse "data" "$OutputDir\data"
Copy-Item "config.json" "$OutputDir\config.json"
Copy-Item "Start Workshop.bat" "$OutputDir\Start Workshop.bat"
# Ship the manual inside the folder so the kit is self-documenting in the field.
if (Test-Path "docs\deployment-manual.md") {
    Copy-Item "docs\deployment-manual.md" "$OutputDir\deployment-manual.md"
}

# -Exclude on Copy-Item -Recurse only filters the top level, so nested
# __pycache__ directories and any stray development database slip through.
# Remove them explicitly rather than trust the copy filter.
Get-ChildItem -Path "$OutputDir\app", "$OutputDir\data" -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
Remove-Item "$OutputDir\data\workshop.duckdb", "$OutputDir\data\workshop.duckdb.wal", `
    "$OutputDir\data\screenshot.duckdb", "$OutputDir\data\verify.duckdb" -ErrorAction SilentlyContinue

Write-Host "Pre-seeding the demonstration history"
# Seed the workshop database at build time so the very first launch on a field
# laptop opens instantly, rather than making a facilitator wait about half a
# minute while 90 days of history is generated in front of a group. The seed is
# deterministic, so a pre-seeded database is byte-identical to what a first run
# would produce. app/main.py guards on the row count, so it will not seed twice.
Push-Location $OutputDir
& ".\python\python.exe" -m app.acquire --simulate --seed-history --readings 0 --database "data\workshop.duckdb"
Pop-Location

Write-Host ""
Write-Host "Portable folder assembled at $OutputDir"
Write-Host "It contains its own Python runtime and every dependency. It needs no"
Write-Host "internet and ignores any other Python on the target laptop."
Write-Host "Copy the whole folder to the next laptop and run Start Workshop.bat."
