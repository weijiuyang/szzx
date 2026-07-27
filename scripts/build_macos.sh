#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller-cache"
HOST_ARCH="$(uname -m)"
MACOS_TARGET_ARCH="${MACOS_TARGET_ARCH:-$HOST_ARCH}"
case "$MACOS_TARGET_ARCH" in
  arm64|x86_64) ;;
  *)
    echo "Unsupported MACOS_TARGET_ARCH: $MACOS_TARGET_ARCH (use arm64 or x86_64)."
    exit 1
    ;;
esac

# Keep the shell and Apple's command-line tools running natively. When building
# Intel binaries on Apple silicon, run only Python/PyInstaller through Rosetta;
# forcing the whole script to x86_64 also forces xcrun/lipo to x86_64 and fails
# with arm64-only Command Line Tools installations.
PYTHON_ARCH_PREFIX=(env)
if [ "$MACOS_TARGET_ARCH" != "$HOST_ARCH" ]; then
  if [ "$HOST_ARCH" = "arm64" ] && [ "$MACOS_TARGET_ARCH" = "x86_64" ]; then
    if ! arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
      echo "Rosetta 2 is required for an x86_64 build on Apple silicon."
      echo "Install it with: softwareupdate --install-rosetta --agree-to-license"
      exit 1
    fi
    PYTHON_ARCH_PREFIX=(arch -x86_64)
  else
    echo "Cross-building $MACOS_TARGET_ARCH on $HOST_ARCH is not supported."
    exit 1
  fi
fi
VENV_DIR=".venv-macos-$MACOS_TARGET_ARCH"
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version="$("${PYTHON_ARCH_PREFIX[@]}" "$candidate" - <<'PY'
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

if [ -x "$VENV_DIR/bin/python" ]; then
  venv_version="$("${PYTHON_ARCH_PREFIX[@]}" "$VENV_DIR/bin/python" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"
  if [[ "$venv_version" == "3.13" ]]; then
    echo "Recreating $VENV_DIR because Python 3.13 is not recommended for packaging."
    rm -rf "$VENV_DIR"
  fi
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  "${PYTHON_ARCH_PREFIX[@]}" "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_ARCH="$("${PYTHON_ARCH_PREFIX[@]}" "$VENV_DIR/bin/python" - <<'PY'
import platform
print(platform.machine().lower())
PY
)"
if [ "$VENV_ARCH" != "$MACOS_TARGET_ARCH" ]; then
  echo "Python architecture $VENV_ARCH does not match target $MACOS_TARGET_ARCH."
  echo "Run this build with a $MACOS_TARGET_ARCH Python environment."
  exit 1
fi

"${PYTHON_ARCH_PREFIX[@]}" "$VENV_DIR/bin/python" -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
"${PYTHON_ARCH_PREFIX[@]}" "$VENV_DIR/bin/python" -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pyinstaller

for path in build dist; do
  if [ -e "$path" ]; then
    chflags -R nouchg,nohidden "$path" 2>/dev/null || true
  fi
done
rm -rf build dist 2>/dev/null || true
for path in build dist; do
  if [ -e "$path" ]; then
    chflags -R nouchg,nohidden "$path" 2>/dev/null || true
    find "$path" -mindepth 1 -maxdepth 1 -exec chflags -R nouchg,nohidden {} \; -exec rm -rf {} \; 2>/dev/null || true
    rm -rf "$path" 2>/dev/null || true
  fi
done
PYINSTALLER_PATH="$PATH"
if [ "$HOST_ARCH" = "arm64" ] && [ "$MACOS_TARGET_ARCH" = "x86_64" ]; then
  # PyInstaller is translated by Rosetta, so its child processes otherwise
  # inherit x86_64 preference. Force Apple's lipo shim back to native arm64.
  PYINSTALLER_PATH="$ROOT_DIR/scripts/macos-native-tools:$PYINSTALLER_PATH"
fi
PATH="$PYINSTALLER_PATH" "${PYTHON_ARCH_PREFIX[@]}" "$VENV_DIR/bin/python" -m PyInstaller \
  --noconfirm \
  --windowed \
  --name SZZXLocalDesk \
  --icon "szzx_local/assets/icon/logo.icns" \
  --osx-bundle-identifier com.szzx.localdesk \
  --target-architecture "$MACOS_TARGET_ARCH" \
  --add-data "szzx_local/assets:szzx_local/assets" \
  --clean \
  run.py

APP_PLIST="dist/SZZXLocalDesk.app/Contents/Info.plist"
if [ -f "$APP_PLIST" ]; then
  APP_VERSION="$("${PYTHON_ARCH_PREFIX[@]}" "$VENV_DIR/bin/python" - <<'PY'
from szzx_local.version import APP_VERSION
print(APP_VERSION)
PY
)"
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$APP_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $APP_VERSION" "$APP_PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$APP_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$APP_PLIST"
  /usr/libexec/PlistBuddy -c "Set :NSLocalNetworkUsageDescription 数智中心需要访问本地网络，用于发现在线同事并同步项目数据。" "$APP_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string 数智中心需要访问本地网络，用于发现在线同事并同步项目数据。" "$APP_PLIST"
fi

# PyInstaller signs the bundle before the metadata above is updated. Re-sign
# after all bundle modifications so the final app has a valid seal.
codesign --force --deep --sign - "dist/SZZXLocalDesk.app"
codesign --verify --deep --strict --verbose=2 "dist/SZZXLocalDesk.app"

if SZZX_LOCAL_DATA_DIR="$ROOT_DIR/.smoke-data" \
  QT_QPA_PLATFORM=offscreen \
  dist/SZZXLocalDesk.app/Contents/MacOS/SZZXLocalDesk --smoke-test; then
  echo "Packaged app smoke test passed."
else
  echo "Packaged app smoke test did not pass on this machine. Continuing to create the DMG."
  echo "For broad distribution on macOS, sign and notarize with an Apple Developer ID."
fi

DMG_PATH="dist/SZZXLocalDesk-mac-$MACOS_TARGET_ARCH.dmg"
rm -f "$DMG_PATH" dist/SZZXLocalDesk-mac.dmg
if hdiutil create \
  -volname "数智中心" \
  -srcfolder dist/SZZXLocalDesk.app \
  -ov \
  -format UDZO \
  -fs HFS+ \
  "$DMG_PATH"; then
  cp "$DMG_PATH" dist/SZZXLocalDesk-mac.dmg
  echo "Built $DMG_PATH"
else
  echo "Built dist/SZZXLocalDesk.app"
  echo "DMG creation failed. You can still distribute the .app, or run hdiutil create manually."
  exit 0
fi

echo "Built dist/SZZXLocalDesk.app"
