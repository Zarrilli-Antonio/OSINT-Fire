#!/usr/bin/env bash
# Build a self-contained OSINT-Fire.app (macOS): Flutter UI + the Python backend frozen with PyInstaller.
# Result: dist/OSINT-Fire.app. Needs: uv, flutter, Xcode command line tools. Ad-hoc signed (fine for running on this Mac).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> backend (PyInstaller)"
(cd backend && uv sync --extra mcp >/dev/null && uv run --with pyinstaller pyinstaller --noconfirm --clean --onedir --name osint-backend \
  --distpath ../build/pyi --workpath ../build/pyi-work --specpath ../build \
  --collect-all maigret --collect-all phonenumbers --collect-all reportlab \
  --collect-submodules uvicorn --collect-submodules dns --collect-submodules osint --collect-data certifi \
  run_backend.py >/dev/null)

echo "==> app (flutter release)"
(cd app && flutter build macos --release)

echo "==> assemble"
APP="$ROOT/dist/OSINT-Fire.app"
rm -rf "$APP"; mkdir -p "$ROOT/dist"
cp -R "$ROOT/app/build/macos/Build/Products/Release/OSINT-Fire.app" "$APP"
mkdir -p "$APP/Contents/Resources/backend"
cp -R "$ROOT/build/pyi/osint-backend/." "$APP/Contents/Resources/backend/"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$APP/Contents/Resources/"  # license and notices travel with the app
codesign --force --deep --sign - "$APP"
echo "done: $APP ($(du -sh "$APP" | cut -f1))"
