# Build a self-contained OSINT-Fire for Windows: Flutter UI + the Python backend frozen with PyInstaller.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
#
# Result: dist\OSINT-Fire\OSINT-Fire.exe  (and dist\OSINT-Fire-windows.zip)
# Needs: uv, Flutter (with the Windows desktop toolchain: Visual Studio 2022 "Desktop development with C++"), Git.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Need($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "Missing '$name'. $hint" }
}
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

Need uv "Install it with: winget install --id=astral-sh.uv -e"
Need flutter "Install Flutter: https://docs.flutter.dev/get-started/install/windows/desktop"

Write-Host "==> backend (PyInstaller)"
Push-Location backend
uv sync --extra mcp | Out-Null; Check "uv sync"
uv run --with pyinstaller pyinstaller --noconfirm --clean --onedir --name osint-backend `
    --distpath ..\build\pyi --workpath ..\build\pyi-work --specpath ..\build `
    --collect-all maigret --collect-all phonenumbers --collect-all reportlab `
    --collect-submodules uvicorn --collect-submodules dns --collect-submodules osint --collect-data certifi `
    run_backend.py | Out-Null
Check "PyInstaller"
Pop-Location

Write-Host "==> app (flutter release)"
Push-Location app
flutter config --enable-windows-desktop | Out-Null
flutter pub get | Out-Null; Check "flutter pub get"
flutter build windows --release; Check "flutter build windows"
Pop-Location

Write-Host "==> assemble"
$Out = Join-Path $Root "dist\OSINT-Fire"
if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item -Recurse -Force "app\build\windows\x64\runner\Release\*" $Out
Copy-Item -Recurse -Force "build\pyi\osint-backend" (Join-Path $Out "backend")   # the app looks for backend\osint-backend.exe next to itself
Copy-Item LICENSE, THIRD_PARTY_NOTICES.md $Out

$Zip = Join-Path $Root "dist\OSINT-Fire-windows.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path "$Out\*" -DestinationPath $Zip
$mb = [math]::Round((Get-ChildItem $Out -Recurse | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "done: $Out ($mb MB)  and  $Zip"
Write-Host "run it with: .\dist\OSINT-Fire\OSINT-Fire.exe"
