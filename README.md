# Karel Switcher — ATEM Controller

A small Tkinter GUI to control a Blackmagic ATEM switcher and trigger cuts via an Arduino. Includes resilient reconnection, cross‑platform serial auto‑detection, .env support, and one‑shot builds for macOS and Linux.

Features
- UI: 4 input tiles (red = Program, green outline = Preview). Keys 1..4 set Preview; Space performs Cut; 0 clears CUE.
- ATEM: Connects via PyATEMMax; auto‑reconnect with exponential backoff and safe command handling.
- Arduino: Reads a simple “1” trigger over serial; auto‑detects ports on macOS/Linux; reconnects on errors.
- Config: Env vars and JSON config with clear precedence so double‑click builds work without Terminal.
- Builds: PyInstaller specs and scripts for macOS (`.app`) and Linux (single executable).

Quick Start (source)
- Python 3 with Tkinter, and `pip install pyserial`
- Run: `python3 run.py`

Configuration
- .env file (optional, loaded first):
  - Looked up at `./.env` (current directory) and next to the executable (for onefile) or this script.
  - Examples:
    - `ATEM_IP=192.168.10.240`
    - `ARDUINO_PORT=/dev/ttyUSB0`
    - `BAUD_RATE=9600`
    - `VIDEO_FILE=/path/to/video.mp4` (for mpv integration)
    - `MPV_SOCKET=/tmp/mpvsocket` (mpv IPC path)
- Environment variables (highest precedence):
  - `ATEM_IP` — e.g., `192.168.10.240`
  - `ARDUINO_PORT` — e.g., `/dev/tty.usbmodemXXXX` (macOS) or `/dev/ttyUSB0` (Linux)
  - `BAUD_RATE` — default `9600`
  - `KAREL_CONFIG` — optional path to a JSON config file
- Config file (first found wins):
  - macOS: `~/Library/Application Support/KarelSwitcher/config.json`
  - Linux: `~/.config/karel/config.json`
  - Project: `karel/config.json`
  - CWD: `./config.json`
- Sample: see `karel/config.sample.json`

Build Binaries
- macOS: `./build-mac.sh`
  - Output: `dist/KarelSwitcher.app`
  - Tip: first run may require Right‑click → Open (Gatekeeper)
- Linux: `./build-linux.sh`
  - Output: `dist/karel-switcher` (single-file executable)
  - Requires Python Tkinter (`sudo apt-get install python3-tk` on Debian/Ubuntu)

Included Scripts
- `run.py` — Main GUI app with reconnection and status indicators.
- `scan.py` — Scan a /24 range for ATEM devices: `python3 scan.py 192.168.10`
- `getch.py` — Minimal UDP probe to read current Program input (example parser).
- `switch_video.py` — Control mpv via IPC to toggle/blend sources (advanced demo).
- `atem-controll.py` — Minimal prototype program switcher (example/stub).
- `run_mpv.py` — Same UI as `run.py` with mpv control: loads `VIDEO_FILE` into mpv via `MPV_SOCKET`, pauses at start; press `P` to arm playback on next CUT.

MPV Integration
- Auto‑launch + fullscreen: `run_mpv.py` auto‑starts mpv if its IPC socket isn’t available, always in fullscreen. On Linux, it prefers a secondary display if detected via `xrandr` (uses `--fs-screen=<monitor>`); otherwise it uses the primary display.
- Manual start (optional):
  - `mpv --input-ipc-server=/tmp/mpvsocket --idle=yes --force-window=yes --fs`
- Set in `.env` (or export variables):
  - `VIDEO_FILE=/absolute/or/relative/path/to/video.mp4`
  - `MPV_SOCKET=/tmp/mpvsocket`
  - `MPV_PATH=mpv` (path to mpv binary, if not on PATH)
  - `MPV_ARGS="--fs-screen=HDMI-1"` (extra flags appended after defaults; use to force a specific screen)
  - `MPV_PLAY_DELAY_MS=0` (delay between CUT trigger and starting playback; default 0)
  - `MPV_STEP_MS=100` (Left/Right arrow seek step in milliseconds; default 100)
- Run from source:
  - `make run-mpv` (or `python3 run_mpv.py`)
- Notes:
  - `MPV_ARGS` are appended after the defaults (`--fs` and optional `--fs-screen=<auto>`), so your values take precedence on duplicates.
  - Secondary‑display detection uses `xrandr --listmonitors` on Linux; if `xrandr` is unavailable or only one display is connected, fullscreen opens on the primary.
  - `MPV_PLAY_DELAY_MS` only affects the mpv start (when armed with `P`) after a CUT; it does not delay the ATEM cut itself.
  - Left/Right arrows pause and seek by `±MPV_STEP_MS` and immediately sync the preview window to the same timestamp.

Troubleshooting
- Serial permissions (Linux): add your user to `dialout` or adjust udev.
- No UI on build: ensure Tkinter is installed for the Python used to bundle.
- macOS networking prompts: allow incoming connections for the app on first run.
- Mixed Mac architectures: build on each architecture (arm64/Intel) to target both.
