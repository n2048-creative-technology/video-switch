#!/usr/bin/env python3
"""
Karel Switcher UI

Overview
- Tkinter UI to control a Blackmagic ATEM switcher and trigger cuts via an Arduino.
- Resilient connections: automatic reconnect/backoff for both ATEM (TCP) and Arduino (serial).
- Cross-platform serial detection for Linux/macOS.
- Configurable via JSON config file and/or environment variables.

Configuration precedence
1) Environment variables: ATEM_IP, ARDUINO_PORT, BAUD_RATE, KAREL_CONFIG
2) Config file (first found):
   - macOS: ~/Library/Application Support/KarelSwitcher/config.json
   - Linux: ~/.config/karel/config.json
   - Project: karel/config.json
   - CWD: ./config.json
3) Built-in defaults.

Usage
- Run from source: python3 karel/run.py
- macOS app: double‑click dist/KarelSwitcher.app; logs visible via its MacOS binary.
- Linux binary: ./dist/karel-switcher

Keyboard
- 1..4 set Preview (CUE). Space triggers Cut to Program (PRG). 0 clears CUE.

Dependencies
- PyATEMMax, pyserial, Tkinter (bundled with Python on most systems).
"""

import tkinter as tk
import time
import os
import sys
import json
import platform
import PyATEMMax
import serial
from serial.tools import list_ports
import threading


def _load_env_file():
    """Load simple KEY=VALUE pairs from a .env file, if present.

    Search order (first existing is used):
    1) Current working directory: ./.env
    2) Directory of the frozen executable (when bundled) or this file
       (when running from source): <exec_dir>/.env

    Only sets variables that are not already present in os.environ so that
    real environment variables still take precedence.
    """
    candidates = []
    # CWD .env
    candidates.append(os.path.join(os.getcwd(), ".env"))
    # Executable directory .env (works for PyInstaller onefile and source run)
    try:
        if getattr(sys, 'frozen', False):
            exec_dir = os.path.dirname(sys.executable)
        else:
            exec_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(exec_dir, ".env"))
    except Exception:
        pass

    env_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not env_path:
        return

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Strip inline comments beginning with ' #' (space hash) or just '#'
                # when not within quotes. Keep this simple.
                if '#' in line and not (line.startswith('"') or line.startswith("'")):
                    line = line.split('#', 1)[0].strip()
                if '=' not in line:
                    continue
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        print(f"Warning: could not read .env file: {e}")


# Load .env before reading any env-based configuration
_load_env_file()

def _config_paths():
    paths = []
    # 1) Explicit override via env var
    env_path = os.getenv("KAREL_CONFIG")
    if env_path:
        paths.append(env_path)
    # 2) OS-specific user config locations
    home = os.path.expanduser("~")
    sysname = platform.system()
    if sysname == "Darwin":
        paths.append(os.path.join(home, "Library", "Application Support", "KarelSwitcher", "config.json"))
    else:
        paths.append(os.path.join(home, ".config", "karel", "config.json"))
    # 3) Project-relative fallbacks (when running from source)
    base_dir = os.path.abspath(os.path.dirname(__file__))
    paths.append(os.path.join(base_dir, "config.json"))
    # 4) CWD fallback
    paths.append(os.path.join(os.getcwd(), "config.json"))
    return paths

def load_config():
    for p in _config_paths():
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"Config read error at {p}: {e}")
    return {}

_CONF = load_config()

# Allow overriding via environment variables; else use config; else default
# ATEM_IP = "172.17.0.79"
ATEM_IP = os.getenv("ATEM_IP", _CONF.get("ATEM_IP", "192.168.10.240"))

ARDUINO_PORT = os.getenv("ARDUINO_PORT", _CONF.get("ARDUINO_PORT", ""))  # Auto-detect if empty
try:
    BAUD_RATE = int(_CONF.get("BAUD_RATE", 9600))
except Exception:
    BAUD_RATE = 9600

def detect_arduino_port():
    """Best-effort serial port auto-detection for Linux/macOS."""
    candidates = []
    for p in list_ports.comports():
        dev = p.device or ""
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        # Common Arduino/USB-serial markers across Linux/macOS
        if any(tag in desc for tag in ["arduino", "ch340", "wchusbserial", "usb serial", "usb-serial", "cp210", "ftdi"]) or \
           any(tag in dev for tag in ["/dev/ttyUSB", "/dev/ttyACM", "/dev/tty.usb", "/dev/tty.SLAB_USB", "/dev/tty.wchusbserial"]):
            candidates.append(dev)
        # Fallback: anything that looks like a tty USB device
        elif dev.startswith("/dev/tty") and ("usb" in dev.lower() or "ACM" in dev or "SLAB" in dev):
            candidates.append(dev)
    return candidates[0] if candidates else None


# Connect to ATEM Mini Pro
switcher = PyATEMMax.ATEMMax()
_atem_lock = threading.Lock()
def _atem_is_connected():
    try:
        return bool(getattr(switcher, "connected", False))
    except Exception:
        return False
def _atem_connect_blocking():
    try:
        with _atem_lock:
            if _atem_is_connected():
                return True
            switcher.connect(ATEM_IP)
            switcher.waitForConnection()
            return _atem_is_connected()
    except Exception as e:
        print(f"ATEM connect error: {e}")
        return False


# Connect to Arduino
ser = None
_serial_port_name = ARDUINO_PORT  # may be empty -> auto
def _serial_try_connect():
    global ser, _serial_port_name
    try:
        port = _serial_port_name or detect_arduino_port()
        if port:
            ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
            _serial_port_name = port
            print(f"Connected to Arduino on {port}")
            return True
        else:
            print("No Arduino serial port found. Running without serial trigger.")
            return False
    except Exception as e:
        print(f"Could not connect to Arduino: {e}")
        try:
            if ser:
                ser.close()
        except Exception:
            pass
        ser = None
        return False

class ChannelSwitcherApp:
    """Tkinter UI for preview/program control and status display.

    - Shows four input tiles; red = Program, green outline = Preview (CUE).
    - Keyboard: 1..4 to set CUE, Space to Cut, 0 to clear CUE.
    - Periodically maintains ATEM and Arduino connections.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Channel Switcher")

        self.PRG = 1
        self.CUE = 1

        # Canvas for rectangles
        self.canvas = tk.Canvas(root, width=600, height=150, bg='lightgrey')
        self.canvas.pack(padx=10, pady=10)

        # Status indicators
        self.status_frame = tk.Frame(root)
        self.status_frame.pack(fill='x', padx=10, pady=(0,10))
        self.atem_status_lbl = tk.Label(self.status_frame, text='ATEM: —', width=30, anchor='w')
        self.arduino_status_lbl = tk.Label(self.status_frame, text='Arduino: —', width=30, anchor='w')
        self.atem_status_lbl.pack(side='left')
        self.arduino_status_lbl.pack(side='left', padx=(10,0))

        # Store rect IDs so we can update them
        self.rects = []
        self.texts = []

        self.draw_rects()
        self.update_status_labels()

        # Bind keys
        for key in ['1', '2', '3', '4', '0']:
            self.root.bind(key, self.on_key)
        self.root.bind('<space>', self.on_key)  # spacebar for cut

        # Backoff state for reconnections
        self.atem_backoff = 1.0
        self.atem_backoff_max = 10.0
        self.serial_backoff = 1.0
        self.serial_backoff_max = 10.0

        # Start periodic tasks
        self.ensure_connections()
        self.poll_serial()

    def draw_rects(self):
        """Render the 4 input tiles with current PRG/CUE state."""
        self.canvas.delete("all")
        start_x, start_y = 20, 20
        rect_w, rect_h, gap = 120, 100, 20

        for i in range(1, 5):
            if i == self.PRG:
                fill = 'red'
            else:
                fill = 'white'
            width = 3

            outline_color = 'black'
            if i == self.CUE and self.CUE != self.PRG:
                outline_color = 'green'
                width = 7

            rect_id = self.canvas.create_rectangle(
                start_x, start_y,
                start_x + rect_w, start_y + rect_h,
                fill=fill, outline=outline_color, width=width
            )
            text_id = self.canvas.create_text(
                start_x + rect_w / 2,
                start_y + rect_h / 2,
                text=str(i), font=('Helvetica', 32, 'bold')
            )
            self.rects.append(rect_id)
            self.texts.append(text_id)
            start_x += rect_w + gap

    def trigger(self):
        """Perform a CUT: set PRG = CUE and send ATEM commands if connected."""
        self.PRG = self.CUE
        try:
            if _atem_is_connected():
                time.sleep(0.05)
                switcher.execCutME(0)
                switcher.setPreviewInputVideoSource(0, self.CUE)
                switcher.setProgramInputVideoSource(0, self.PRG)  # not needed
                time.sleep(0.2)
            else:
                # Trigger reconnection attempts ASAP
                self.atem_backoff = 1.0
        except Exception as e:
            print(f"ATEM command error: {e}")
            self.atem_backoff = 1.0
        self.update_display()

    def on_key(self, event):
        """Handle keyboard events for CUE selection and CUT trigger."""
        if event.char in ['1', '2', '3', '4']:
            self.CUE = int(event.char)
            try:
                if _atem_is_connected():
                    switcher.setPreviewInputVideoSource(0, self.CUE)
                else:
                    self.atem_backoff = 1.0
            except Exception as e:
                print(f"ATEM preview set error: {e}")
                self.atem_backoff = 1.0
        if event.char == '0':
            self.CUE = 0
        elif event.keysym == 'space':
           self.trigger()
        
        self.update_display()

    def update_display(self):
        """Refresh the canvas and status labels."""
        self.draw_rects()
        self.update_status_labels()

    def update_status_labels(self):
        atem_ok = _atem_is_connected()
        arduino_ok = bool(ser and getattr(ser, 'is_open', False))
        # Details
        atem_text = f"ATEM ({ATEM_IP}): {'Connected' if atem_ok else 'Disconnected'}"
        port_name = None
        try:
            port_name = ser.port if (ser and ser.is_open) else (_serial_port_name or 'auto')
        except Exception:
            port_name = _serial_port_name or 'auto'
        arduino_text = f"Arduino ({port_name}): {'Connected' if arduino_ok else 'Disconnected'}"

        self.atem_status_lbl.config(text=atem_text, fg=('green' if atem_ok else 'red'))
        self.arduino_status_lbl.config(text=arduino_text, fg=('green' if arduino_ok else 'red'))

    def poll_serial(self):
        """Check Arduino serial for '1' and trigger action. Reconnect on errors."""
        global ser
        try:
            if ser and ser.is_open and ser.in_waiting:
                data = ser.readline().decode('utf-8', errors='ignore').strip()
                if data == "1":
                    time.sleep(0.2)
                    self.trigger()
        except Exception as e:
            print(f"Serial read error: {e}")
            try:
                if ser:
                    ser.close()
            except Exception:
                pass
            ser = None
            # So that ensure_connections will try sooner
            self.serial_backoff = 1.0

        # Schedule next check in 50 ms
        self.root.after(50, self.poll_serial)

    def ensure_connections(self):
        """Maintain stable connections to ATEM and Arduino with backoff retries."""
        # ATEM reconnect
        if not _atem_is_connected():
            def _connect_atem_async():
                ok = _atem_connect_blocking()
                if ok:
                    print("ATEM connected")
                    try:
                        switcher.setAudioMixerMasterVolume(0)
                        # Optionally set initial inputs
                        switcher.setProgramInputVideoSource(0, self.PRG)
                        switcher.setPreviewInputVideoSource(0, self.CUE)
                    except Exception as e:
                        print(f"ATEM post-connect init error: {e}")
                    self.atem_backoff = 1.0
                else:
                    self.atem_backoff = min(self.atem_backoff * 2.0, self.atem_backoff_max)

            threading.Thread(target=_connect_atem_async, daemon=True).start()
        else:
            self.atem_backoff = 1.0

        # Serial reconnect
        global ser
        if not (ser and getattr(ser, 'is_open', False)):
            ok = _serial_try_connect()
            if ok:
                self.serial_backoff = 1.0
            else:
                self.serial_backoff = min(self.serial_backoff * 2.0, self.serial_backoff_max)
        else:
            self.serial_backoff = 1.0

        # Re-run after the smaller backoff among the two (converted to ms)
        delay_s = min(self.atem_backoff, self.serial_backoff)
        delay_ms = int(max(200, delay_s * 1000))
        # Update UI status as well
        self.update_status_labels()
        self.root.after(delay_ms, self.ensure_connections)

def main():
    if _atem_is_connected():
        try:
            switcher.setProgramInputVideoSource(0, 1)
        except Exception as e:
            print(f"ATEM initial program set error: {e}")
    root = tk.Tk()
    app = ChannelSwitcherApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
