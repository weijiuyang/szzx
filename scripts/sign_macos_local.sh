#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

APP_PATH="${1:-dist/SZZXLocalDesk.app}"
IDENTITY="${2:-}"

if [ ! -d "$APP_PATH" ]; then
  echo "App not found: $APP_PATH"
  exit 1
fi

if [ -z "$IDENTITY" ]; then
  IDENTITY="$(security find-identity -v -p codesigning | awk -F '"' '/Developer ID Application|Apple Development/ { print $2; exit }')"
fi

if [ -z "$IDENTITY" ]; then
  echo "No Apple code signing identity was found."
  echo "Install an Apple Development or Developer ID Application certificate, then run:"
  echo "  ./scripts/sign_macos_local.sh \"$APP_PATH\" \"CERTIFICATE NAME\""
  exit 1
fi

xattr -dr com.apple.quarantine "$APP_PATH" 2>/dev/null || true
codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
spctl --assess --type execute --verbose=4 "$APP_PATH" || true

echo "Signed $APP_PATH with: $IDENTITY"
