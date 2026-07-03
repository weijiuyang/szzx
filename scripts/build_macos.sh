#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller-cache"
MACOS_TARGET_ARCH="${MACOS_TARGET_ARCH:-universal2}"

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$($candidate - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
)"
    if [[ "$version" != 3.13* ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.12/3.11/3.10 is required for packaging. Install the official macOS Python from https://www.python.org/downloads/macos/ and rerun this script."
  exit 1
fi

if [ -x ".venv/bin/python" ]; then
  venv_version="$(.venv/bin/python - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  if [[ "$venv_version" == "3.13" ]]; then
    echo "Recreating .venv because Python 3.13 is not recommended for packaging."
    rm -rf .venv
  fi
fi

if [ ! -x ".venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
.venv/bin/python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pyinstaller

for path in build dist; do
  if [ -e "$path" ]; then
    chflags -R nouchg,nohidden "$path" 2>/dev/null || true
  fi
done
rm -rf build dist
for path in build dist; do
  if [ -e "$path" ]; then
    find "$path" -mindepth 1 -maxdepth 1 -exec chflags -R nouchg,nohidden {} \; -exec rm -rf {} \; 2>/dev/null || true
    rmdir "$path" 2>/dev/null || true
  fi
done
rm -rf .packaging-assets
mkdir -p .packaging-assets
rsync -a \
  --exclude '.DS_Store' \
  --exclude '*.mp4' \
  szzx_local/assets/ .packaging-assets/assets/
.venv/bin/pyinstaller \
  --noconfirm \
  --windowed \
  --name SZZXLocalDesk \
  --osx-bundle-identifier com.szzx.localdesk \
  --target-architecture "$MACOS_TARGET_ARCH" \
  --add-data ".packaging-assets/assets:szzx_local/assets" \
  --clean \
  run.py
rm -rf .packaging-assets

if SZZX_LOCAL_DATA_DIR="$ROOT_DIR/.smoke-data" \
  QT_QPA_PLATFORM=offscreen \
  dist/SZZXLocalDesk.app/Contents/MacOS/SZZXLocalDesk --smoke-test; then
  echo "Packaged app smoke test passed."
else
  echo "Packaged app smoke test did not pass on this machine. Continuing to create the DMG."
  echo "For broad distribution on macOS, sign and notarize with an Apple Developer ID."
fi

rm -f dist/SZZXLocalDesk-mac.dmg
if hdiutil create \
  -volname "数智中心" \
  -srcfolder dist/SZZXLocalDesk.app \
  -ov \
  -format UDZO \
  -fs HFS+ \
  dist/SZZXLocalDesk-mac.dmg; then
  echo "Built dist/SZZXLocalDesk-mac.dmg"
else
  echo "Built dist/SZZXLocalDesk.app"
  echo "DMG creation failed. You can still distribute the .app, or run hdiutil create manually."
  exit 0
fi

echo "Built dist/SZZXLocalDesk.app"
