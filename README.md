# Karel Switcher — ATEM Video Switcher Controller

**Status: FINISHED / actively usable tool.** Built for live video-switching setups (installations,
events, performances) using a Blackmagic ATEM switcher triggered by a physical Arduino button, with
optional mpv video playback integration. Packaged as standalone builds for macOS and Linux so it can
be run without a terminal on-site.

## What it does

A small Tkinter GUI that:

- Connects to a Blackmagic ATEM video switcher over the network (via `PyATEMMax`) and shows 4 input
  tiles (red = currently on Program, green outline = current Preview).
- Lets you set Preview (keys `1`-`4`), perform a Cut (`Space`), and clear cue (`0`).
- Listens on a serial connection to an Arduino sending a simple "1" trigger byte (e.g. a physical
  button/sensor) to fire a Cut remotely — with auto-detection of the serial port and automatic
  reconnection if the ATEM or Arduino connection drops.
- Optionally drives `mpv` video playback via its IPC socket (`run_mpv.py`), so a Cut on the switcher
  can also trigger/sync local video playback — useful for installations where a physical trigger
  needs to both switch a live camera feed and start a video.

## Repo layout

- `run.py` — main GUI app (ATEM + Arduino trigger, reconnection, status indicators).
- `run_mpv.py` — same UI as `run.py`, plus mpv playback control (auto-launch, fullscreen, seek).
- `scan.py` — scans a /24 subnet for ATEM devices (`python3 scan.py 192.168.10`).
- `switch_video.py` — advanced demo: controls mpv via IPC to toggle/blend video sources.
- `atem-controll.py`, `getch.py` — minimal prototype/example scripts.
- `pulse-receiver/pulse-receiver.ino` — Arduino sketch companion (sends the serial trigger).
- `PyATEMMax/` — vendored ATEM protocol library.
- `keyboard/`, `pynput/`, `serial_asyncio/` — vendored third-party Python dependencies (bundled for
  offline/onefile builds).
- `build-mac.sh`, `build-linux.sh`, `karel-*.spec` — PyInstaller build scripts/specs producing a
  double-clickable macOS `.app` or a single-file Linux executable.
- `release/` — prebuilt release archives, checksums, and release notes for past versions.

## Quick start (from source)

Requires Python 3 with Tkinter, plus `pyserial`:

```bash
pip install pyserial
python3 run.py
```

## Configuration

Set via `.env` (see `.env.template`) or environment variables (env vars take precedence):

- `ATEM_IP` — e.g. `192.168.10.240`
- `ARDUINO_PORT` — e.g. `/dev/ttyUSB0` (Linux) or `/dev/tty.usbmodemXXXX` (macOS)
- `BAUD_RATE` — default `9600`
- `KAREL_CONFIG` — optional path to a JSON config file (see `config.sample.json`)

For mpv integration, also set `VIDEO_FILE`, `MPV_SOCKET`, `MPV_PATH`, `MPV_ARGS`,
`MPV_PLAY_DELAY_MS`, `MPV_STEP_MS` — see inline docs in `run_mpv.py`.

## Building standalone binaries

- macOS: `./build-mac.sh` → `dist/KarelSwitcher.app` (first run: right-click → Open, for Gatekeeper)
- Linux: `./build-linux.sh` → `dist/karel-switcher` (requires `python3-tk`)

## Dependencies

- Python 3, Tkinter, `pyserial`
- `PyATEMMax` (vendored) for ATEM protocol
- `mpv` (optional, for video playback integration)
- PyInstaller (for building standalone binaries)

## Troubleshooting

- Linux serial permissions: add your user to `dialout` or adjust udev rules.
- No UI on a built binary: ensure Tkinter is installed for the Python used to bundle it.
- macOS: allow incoming network connections for the app on first run.
