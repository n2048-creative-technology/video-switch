
#!/usr/bin/env python3
"""
Karel Switcher UI + MPV trigger

Adds simple mpv (media player) IPC integration to the base UI:
- At app start, loads the video defined in .env (VIDEO_FILE) into a running
  mpv instance via its IPC socket (MPV_SOCKET), seeks to the beginning, and pauses.
- If the user presses 'P', the next CUT trigger will also start playback.

Environment (.env supported; see README):
- ATEM_IP, ARDUINO_PORT, BAUD_RATE — same as run.py
- VIDEO_FILE — absolute or relative path to a media file to load in mpv
- MPV_SOCKET — path to mpv's IPC (default: /tmp/mpvsocket)

Notes:
- Start mpv separately with IPC enabled, for example:
  mpv --input-ipc-server=/tmp/mpvsocket --idle=yes --force-window=yes
"""

import tkinter as tk
import time
import os
import sys
import json
import platform
import socket
import subprocess
import shutil
import shlex
import serial
from serial.tools import list_ports
import threading


def _load_env_file():
    """Load simple KEY=VALUE pairs from a .env file, if present."""
    candidates = [os.path.join(os.getcwd(), ".env")]
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


_load_env_file()

def _config_paths():
    paths = []
    env_path = os.getenv("KAREL_CONFIG")
    if env_path:
        paths.append(env_path)
    home = os.path.expanduser("~")
    sysname = platform.system()
    if sysname == "Darwin":
        paths.append(os.path.join(home, "Library", "Application Support", "KarelSwitcher", "config.json"))
    else:
        paths.append(os.path.join(home, ".config", "karel", "config.json"))
    base_dir = os.path.abspath(os.path.dirname(__file__))
    paths.append(os.path.join(base_dir, "config.json"))
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

ATEM_IP = os.getenv("ATEM_IP", _CONF.get("ATEM_IP", "192.168.10.240"))
ARDUINO_PORT = os.getenv("ARDUINO_PORT", _CONF.get("ARDUINO_PORT", ""))
try:
    BAUD_RATE = int(os.getenv("BAUD_RATE", _CONF.get("BAUD_RATE", 9600)))
except Exception:
    BAUD_RATE = 9600

# MPV integration
MPV_SOCKET = os.getenv("MPV_SOCKET", _CONF.get("MPV_SOCKET", "/tmp/mpvsocket"))
MPV_PATH = os.getenv("MPV_PATH", _CONF.get("MPV_PATH", "mpv"))
MPV_ARGS = os.getenv("MPV_ARGS", _CONF.get("MPV_ARGS", ""))
VIDEO_FILE = os.getenv("VIDEO_FILE", _CONF.get("VIDEO_FILE", ""))


def mpv_send(payload):
    """Send a JSON IPC payload to mpv's UNIX socket. Returns response or None."""
    if not MPV_SOCKET:
        return None
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.2)
        client.connect(MPV_SOCKET)
        msg = (json.dumps(payload) + "\n").encode("utf-8")
        client.sendall(msg)
        try:
            data = client.recv(4096)
            if data:
                return json.loads(data.decode("utf-8"))
        except Exception:
            pass
    except Exception as e:
        # Keep quiet to not spam; the status line will show mpv state
        print(f"mpv IPC error: {e}")
    finally:
        try:
            client.close()
        except Exception:
            pass
    return None


def mpv_load_and_pause(path):
    if not path:
        return False
    # Load file, pause and seek to start
    mpv_send({"command": ["loadfile", path, "replace"]})
    time.sleep(0.05)
    mpv_send({"command": ["set_property", "pause", True]})
    mpv_send({"command": ["set_property", "time-pos", 0]})
    return True


def mpv_play():
    mpv_send({"command": ["set_property", "pause", False]})


def _mpv_ipc_ready():
    try:
        resp = mpv_send({"command": ["get_property", "pause"]})
        return isinstance(resp, dict) and resp.get('error') == 'success'
    except Exception:
        return False


_mpv_proc = None


def launch_mpv_if_needed():
    global _mpv_proc
    if _mpv_ipc_ready():
        return True
    # Find mpv binary
    mpv_bin = MPV_PATH if os.path.isabs(MPV_PATH) or os.path.sep in MPV_PATH else (shutil.which(MPV_PATH) or MPV_PATH)
    if not shutil.which(mpv_bin) and not os.path.isabs(mpv_bin):
        print(f"mpv not found on PATH (MPV_PATH={MPV_PATH}).")
        return False
    # Detect a secondary monitor for fullscreen if possible (X11).
    def _detect_secondary_monitor_name():
        try:
            if platform.system() != "Linux":
                return None
            if not shutil.which("xrandr"):
                return None
            out = subprocess.check_output(["xrandr", "--listmonitors"], text=True, stderr=subprocess.DEVNULL)
            primary = None
            names = []
            for line in out.splitlines():
                line = line.strip()
                if not line or line.startswith("Monitors:"):
                    continue
                # Example line: "0: +*eDP-1 1920/344x1080/194+0+0  eDP-1"
                tok = (line.split()[1] if len(line.split()) > 1 else "")
                name = tok.lstrip("+*")
                if "*" in tok:
                    primary = name
                names.append(name)
            if len(names) >= 2:
                # Prefer any non-primary output
                for n in names:
                    if n != primary:
                        return n
                return names[1]
        except Exception:
            return None
        return None

    # Build command
    cmd = [mpv_bin, f"--input-ipc-server={MPV_SOCKET}", "--idle=yes", "--force-window=yes", "--fs"]
    sec = _detect_secondary_monitor_name()
    if sec:
        cmd.append(f"--fs-screen={sec}")
    extra = shlex.split(MPV_ARGS) if MPV_ARGS else []
    cmd.extend(extra)
    try:
        _mpv_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Failed to start mpv: {e}")
        return False
    # Wait up to ~5s for IPC to be ready
    for _ in range(50):
        if _mpv_ipc_ready():
            return True
        time.sleep(0.1)
    print("mpv IPC not ready after launch.")
    return False


# PyATEMMax connection
import PyATEMMax

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


# Serial connection
ser = None
_serial_port_name = ARDUINO_PORT


def detect_arduino_port():
    candidates = []
    for p in list_ports.comports():
        dev = p.device or ""
        desc = (p.description or "").lower()
        if any(tag in desc for tag in ["arduino", "ch340", "wchusbserial", "usb serial", "usb-serial", "cp210", "ftdi"]) or \
           any(tag in dev for tag in ["/dev/ttyUSB", "/dev/ttyACM", "/dev/tty.usb", "/dev/tty.SLAB_USB", "/dev/tty.wchusbserial"]):
            candidates.append(dev)
        elif dev.startswith("/dev/tty") and ("usb" in dev.lower() or "ACM" in dev or "SLAB" in dev):
            candidates.append(dev)
    return candidates[0] if candidates else None


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
    def __init__(self, root):
        self.root = root
        self.root.title("Channel Switcher + MPV")

        self.PRG = 1
        self.CUE = 1
        self.play_on_next_trigger = False

        self.canvas = tk.Canvas(root, width=600, height=170, bg='lightgrey')
        self.canvas.pack(padx=10, pady=10)

        self.status_frame = tk.Frame(root)
        self.status_frame.pack(fill='x', padx=10, pady=(0, 10))
        self.atem_status_lbl = tk.Label(self.status_frame, text='ATEM: —', width=30, anchor='w')
        self.arduino_status_lbl = tk.Label(self.status_frame, text='Arduino: —', width=30, anchor='w')
        self.mpv_status_lbl = tk.Label(self.status_frame, text='MPV: —', width=30, anchor='w')
        self.atem_status_lbl.pack(side='left')
        self.arduino_status_lbl.pack(side='left', padx=(10, 0))
        self.mpv_status_lbl.pack(side='left', padx=(10, 0))

        self.rects = []
        self.texts = []
        self.draw_rects()
        self.update_status_labels()

        for key in ['1', '2', '3', '4', '0', 'p', 'P']:
            self.root.bind(key, self.on_key)
        self.root.bind('<space>', self.on_key)

        self.atem_backoff = 1.0
        self.atem_backoff_max = 10.0
        self.serial_backoff = 1.0
        self.serial_backoff_max = 10.0

        # Ensure mpv is running and IPC is ready; then preload video (if configured)
        launch_mpv_if_needed()
        self._mpv_loaded = False
        if VIDEO_FILE:
            if os.path.isfile(VIDEO_FILE):
                ok = mpv_load_and_pause(VIDEO_FILE)
                self._mpv_loaded = ok
            else:
                print(f"VIDEO_FILE not found: {VIDEO_FILE}")

        self.ensure_connections()
        self.poll_serial()

    def draw_rects(self):
        self.canvas.delete("all")
        start_x, start_y = 20, 20
        rect_w, rect_h, gap = 120, 100, 20

        for i in range(1, 5):
            fill = 'red' if i == self.PRG else 'white'
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
            text = str(i)
            if self.play_on_next_trigger and i == self.CUE:
                text += " ▶"
            text_id = self.canvas.create_text(
                start_x + rect_w / 2,
                start_y + rect_h / 2,
                text=text, font=('Helvetica', 32, 'bold')
            )
            self.rects.append(rect_id)
            self.texts.append(text_id)
            start_x += rect_w + gap

        # Hint line
        self.canvas.create_text(
            300, 145,
            text="Keys: 1..4 CUE, Space CUT, 0 clear, P play-on-cut",
            font=('Helvetica', 11)
        )

    def trigger(self):
        self.PRG = self.CUE
        try:
            if _atem_is_connected():
                time.sleep(0.05)
                switcher.execCutME(0)
                switcher.setPreviewInputVideoSource(0, self.CUE)
                switcher.setProgramInputVideoSource(0, self.PRG)
                time.sleep(0.2)
            else:
                self.atem_backoff = 1.0
        except Exception as e:
            print(f"ATEM command error: {e}")
            self.atem_backoff = 1.0

        # If requested, start mpv playback on this trigger
        if self.play_on_next_trigger:
            mpv_play()
            self.play_on_next_trigger = False

        self.update_display()

    def on_key(self, event):
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
        elif event.char in ['p', 'P']:
            # Arm playback on next trigger; try to preload if not already
            if VIDEO_FILE and not self._mpv_loaded and os.path.isfile(VIDEO_FILE):
                self._mpv_loaded = mpv_load_and_pause(VIDEO_FILE)
            self.play_on_next_trigger = True
        self.update_display()

    def update_display(self):
        self.draw_rects()
        self.update_status_labels()

    def update_status_labels(self):
        atem_ok = _atem_is_connected()
        arduino_ok = bool(ser and getattr(ser, 'is_open', False))
        atem_text = f"ATEM ({ATEM_IP}): {'Connected' if atem_ok else 'Disconnected'}"
        try:
            port_name = ser.port if (ser and ser.is_open) else (_serial_port_name or 'auto')
        except Exception:
            port_name = _serial_port_name or 'auto'
        arduino_text = f"Arduino ({port_name}): {'Connected' if arduino_ok else 'Disconnected'}"

        # mpv: simple check by trying to get 'pause' property
        mpv_ok = False
        try:
            resp = mpv_send({"command": ["get_property", "pause"]})
            mpv_ok = isinstance(resp, dict) and resp.get('error') == 'success'
        except Exception:
            mpv_ok = False
        mpv_text = f"MPV ({MPV_SOCKET}): {'Ready' if mpv_ok else 'No IPC'}"

        self.atem_status_lbl.config(text=atem_text, fg=('green' if atem_ok else 'red'))
        self.arduino_status_lbl.config(text=arduino_text, fg=('green' if arduino_ok else 'red'))
        self.mpv_status_lbl.config(text=mpv_text, fg=('green' if mpv_ok else 'red'))

    def poll_serial(self):
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
            self.serial_backoff = 1.0
        self.root.after(50, self.poll_serial)

    def ensure_connections(self):
        if not _atem_is_connected():
            def _connect_atem_async():
                ok = _atem_connect_blocking()
                if ok:
                    print("ATEM connected")
                    try:
                        switcher.setAudioMixerMasterVolume(0)
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

        global ser
        if not (ser and getattr(ser, 'is_open', False)):
            ok = _serial_try_connect()
            if ok:
                self.serial_backoff = 1.0
            else:
                self.serial_backoff = min(self.serial_backoff * 2.0, self.serial_backoff_max)
        else:
            self.serial_backoff = 1.0

        delay_s = min(self.atem_backoff, self.serial_backoff)
        delay_ms = int(max(200, delay_s * 1000))
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
