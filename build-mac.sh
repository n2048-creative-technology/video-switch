#!/usr/bin/env bash
set -euo pipefail

# Build a macOS app bundle for the Karel ATEM controller.
# Usage (from repo root):
#   ATEM_IP=192.168.10.240 ARDUINO_PORT=/dev/tty.usbmodemXXXX ./build-mac.sh

# Always operate from this script's directory (repo root)
cd "$(dirname "$0")"

PY_VER=${PY_VER:-python3}
VENV_DIR=${VENV_DIR:-.venv-macbuild}

if ! command -v ${PY_VER} >/dev/null 2>&1; then
  echo "${PY_VER} not found. Please install Python 3 from python.org (universal2)." >&2
  exit 1
fi

${PY_VER} -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip wheel setuptools

# Dependencies: PyInstaller (packaging) and pyserial (runtime)
python -m pip install pyinstaller pyserial

# Build GUI app bundle and one-file mpv variant
pyinstaller -y ./karel-mac.spec
pyinstaller -y ./karel-mac-mpv.spec

echo
echo "Build complete. Artifacts:"
echo "  - dist/KarelSwitcher.app (double-clickable GUI app)"
echo "  - dist/karel-switcher-mpv (one-file CLI binary with mpv integration)"
echo
echo "Notes:"
echo "- On first run, macOS Gatekeeper may block the app; use Right-click -> Open."
echo "- If your Mac is Apple Silicon, this builds arm64. Build on an Intel Mac for x86_64."
echo "- You can preset ATEM_IP and ARDUINO_PORT using a .env file:"
echo "    - Place .env in the folder you launch from, or inside the app at:"
echo "      dist/KarelSwitcher.app/Contents/MacOS/.env"
echo "    - Or export real environment variables before launching."
