#!/usr/bin/env bash
set -euo pipefail

# Build a Linux executable for the Karel ATEM controller.
# Usage (from repo root):
#   ATEM_IP=192.168.10.240 ARDUINO_PORT=/dev/ttyUSB0 ./build-linux.sh

# Always operate from this script's directory (repo root)
cd "$(dirname "$0")"

PY_VER=${PY_VER:-python3}
VENV_DIR=${VENV_DIR:-.venv-linuxbuild}

if ! command -v ${PY_VER} >/dev/null 2>&1; then
  echo "${PY_VER} not found. Please install Python 3." >&2
  exit 1
fi

# Tkinter runtime is needed for bundling GUI apps.
if ! python3 - <<'PY'
import tkinter as tk
print('ok')
PY
then
  echo "Python Tkinter not available. On Debian/Ubuntu: sudo apt-get install python3-tk" >&2
  exit 1
fi

echo "Creating local virtualenv at ${VENV_DIR}"
${PY_VER} -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip wheel setuptools
# Ensure required tools/libraries for build and runtime are present in the venv
python -m pip install pyinstaller pyserial

# Build using the Linux spec which includes vendored PyATEMMax
pyinstaller -y ./karel-linux.spec

echo
echo "Build complete. Artifacts:"
echo "  - dist/karel-switcher (single-file executable)"
echo
echo "Run with logs visible:"
echo "  ATEM_IP=... ARDUINO_PORT=... ./dist/karel-switcher"
echo "  (or create a .env in CWD or next to the executable)"
echo
echo "Notes:"
echo "- Ensure your system has network access to the ATEM IP."
echo "- If serial device requires permissions, add your user to the 'dialout' group or adjust udev rules."
