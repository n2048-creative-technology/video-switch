
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
import tkinter.simpledialog as simpledialog
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


def _config_write_path():
    """Preferred path to persist config changes."""
    env_path = os.getenv("KAREL_CONFIG")
    if env_path:
        return env_path
    home = os.path.expanduser("~")
    if platform.system() == "Darwin":
        return os.path.join(home, "Library", "Application Support", "KarelSwitcher", "config.json")
    else:
        return os.path.join(home, ".config", "karel", "config.json")


def _ensure_parent_dir(path: str):
    try:
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)
    except Exception as e:
        print(f"Ensure dir failed for {path}: {e}")


def save_config_value(key: str, value):
    """Persist a single key/value into config.json; merges existing content."""
    path = _config_write_path()
    _ensure_parent_dir(path)
    data = {}
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}
    data[str(key)] = value
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Failed to write {path}: {e}")


def _env_candidate_paths():
    """Return candidate .env paths in load order (cwd, script dir)."""
    paths = [os.path.join(os.getcwd(), ".env")]
    try:
        if getattr(sys, 'frozen', False):
            exec_dir = os.path.dirname(sys.executable)
        else:
            exec_dir = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.join(exec_dir, ".env"))
    except Exception:
        pass
    return paths


def save_env_value(key: str, value: str) -> bool:
    """Best-effort update or append KEY=VALUE to a .env file. Returns True if written."""
    targets = [p for p in _env_candidate_paths() if os.path.isfile(p)]
    target = targets[0] if targets else os.path.join(os.getcwd(), ".env")
    try:
        lines = []
        if os.path.isfile(target):
            with open(target, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        key_prefix = f"{key}="
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(key_prefix):
                new_lines.append(f"{key}={value}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{key}={value}")
        with open(target, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")
        return True
    except Exception as e:
        print(f"Failed to write .env: {e}")
    return False


_CONF = load_config()

ATEM_IP = os.getenv("ATEM_IP", _CONF.get("ATEM_IP", "192.168.10.240"))
ARDUINO_PORT = os.getenv("ARDUINO_PORT", _CONF.get("ARDUINO_PORT", ""))
try:
    BAUD_RATE = int(os.getenv("BAUD_RATE", _CONF.get("BAUD_RATE", 9600)))
except Exception:
    BAUD_RATE = 9600

# Arduino trigger delay (ms) before firing CUT after a serial '1' is read
try:
    ARDUINO_TRIGGER_DELAY_MS = int(os.getenv(
        "ARDUINO_TRIGGER_DELAY_MS",
        str(_CONF.get("ARDUINO_TRIGGER_DELAY_MS", "100"))
    ))
except Exception:
    ARDUINO_TRIGGER_DELAY_MS = 100

# MPV integration
MPV_SOCKET = os.getenv("MPV_SOCKET", _CONF.get("MPV_SOCKET", "/tmp/mpvsocket"))
MPV_PATH = os.getenv("MPV_PATH", _CONF.get("MPV_PATH", "mpv"))
MPV_ARGS = os.getenv("MPV_ARGS", _CONF.get("MPV_ARGS", ""))
VIDEO_FILE = os.getenv("VIDEO_FILE", _CONF.get("VIDEO_FILE", ""))
try:
    MPV_PLAY_DELAY_MS = int(os.getenv("MPV_PLAY_DELAY_MS", str(_CONF.get("MPV_PLAY_DELAY_MS", "0"))))
except Exception:
    MPV_PLAY_DELAY_MS = 0


# Extra MPV (preview) integration
def _as_bool(x: str) -> bool:
    return str(x).strip().lower() in ("1", "true", "yes", "on")

MPV_PREVIEW_ENABLE = _as_bool(os.getenv("MPV_PREVIEW_ENABLE", str(_CONF.get("MPV_PREVIEW_ENABLE", "1"))))
MPV_PREVIEW_SOCKET = os.getenv(
    "MPV_PREVIEW_SOCKET",
    _CONF.get("MPV_PREVIEW_SOCKET", (MPV_SOCKET + ".prev") if MPV_SOCKET else "/tmp/mpvsocket_prev")
)
# Default: small, borderless, on top, audio muted
MPV_PREVIEW_ARGS = os.getenv(
    "MPV_PREVIEW_ARGS",
    _CONF.get("MPV_PREVIEW_ARGS", "--geometry=25%x25%+20+20 --no-border --ontop --mute=yes --no-audio --keep-open=always")
)

def _as_bool(x: str) -> bool:
    return str(x).strip().lower() in ("1", "true", "yes", "on")

MPV_SYNC_ENABLE = _as_bool(os.getenv("MPV_SYNC_ENABLE", str(_CONF.get("MPV_SYNC_ENABLE", "1"))))
MPV_SYNC_INTERVAL_MS = int(os.getenv("MPV_SYNC_INTERVAL_MS", str(_CONF.get("MPV_SYNC_INTERVAL_MS", "150"))))  # ~6Hz
MPV_SYNC_DRIFT_SEC = float(os.getenv("MPV_SYNC_DRIFT_SEC", str(_CONF.get("MPV_SYNC_DRIFT_SEC", "0.08"))))

def mpv_send_to(sock_path, payload):
    """Send JSON IPC payload to a specific mpv UNIX socket."""
    if not sock_path:
        return None
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(0.2)
        client.connect(sock_path)
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        try:
            data = client.recv(4096)
            if data:
                return json.loads(data.decode("utf-8"))
        except Exception:
            pass
    except Exception as e:
        # keep quiet-ish; caller decides what to log
        # print(f"mpv IPC({sock_path}) error: {e}")
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass
    return None

def mpv_get(sock_path, prop, default=None):
    try:
        resp = mpv_send_to(sock_path, {"command": ["get_property", prop]})
        if isinstance(resp, dict) and resp.get("error") == "success":
            return resp.get("data")
    except Exception:
        pass
    return default

def mpv_set(sock_path, prop, value):
    mpv_send_to(sock_path, {"command": ["set_property", prop, value]})

def _mpv_ipc_ready_socket(sock_path):
    try:
        resp = mpv_send_to(sock_path, {"command": ["get_property", "pause"]})
        return isinstance(resp, dict) and resp.get("error") == "success"
    except Exception:
        return False


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
    # Load on program
    mpv_send({"command": ["loadfile", path, "replace"]})
    time.sleep(0.05)
    mpv_send({"command": ["set_property", "pause", True]})
    mpv_send({"command": ["set_property", "time-pos", 0]})
    # Load on preview too (best-effort)
    if MPV_PREVIEW_ENABLE and MPV_PREVIEW_SOCKET:
        mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["loadfile", path, "replace"]})
        time.sleep(0.02)
        mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["set_property", "pause", True]})
        mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["set_property", "time-pos", 0]})
    return True

def mpv_play():
    mpv_send({"command": ["set_property", "pause", False]})
    if MPV_PREVIEW_ENABLE and MPV_PREVIEW_SOCKET:
        mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["set_property", "pause", False]})


def _mpv_ipc_ready():
    try:
        resp = mpv_send({"command": ["get_property", "pause"]})
        return isinstance(resp, dict) and resp.get('error') == 'success'
    except Exception:
        return False


_mpv_proc = None

def launch_mpv_if_needed():
    """
    Ensure TWO mpv instances are running with IPC:
      - Program (fullscreen) on MPV_SOCKET
      - Preview (small, muted) on MPV_PREVIEW_SOCKET  (if MPV_PREVIEW_ENABLE)

    Returns True if the program instance is ready (preview is best-effort).
    """
    global _mpv_proc

    def _ensure_dir_for(sock_path):
        try:
            d = os.path.dirname(sock_path) or "."
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            print(f"Cannot ensure socket dir for {sock_path}: {e}")

    def _detect_secondary_monitor_name():
        try:
            if platform.system() != "Linux" or not shutil.which("xrandr"):
                return None
            out = subprocess.check_output(["xrandr", "--listmonitors"], text=True, stderr=subprocess.DEVNULL)
            primary = None
            names = []
            for line in out.splitlines():
                line = line.strip()
                if not line or line.startswith("Monitors:"):
                    continue
                tok = (line.split()[1] if len(line.split()) > 1 else "")
                name = tok.lstrip("+*")
                if "*" in tok:
                    primary = name
                names.append(name)
            if len(names) >= 2:
                for n in names:
                    if n != primary:
                        return n
        except Exception:
            return None
        return None

    # Resolve mpv binary
    mpv_bin = MPV_PATH if (os.path.isabs(MPV_PATH) or os.path.sep in MPV_PATH) else (shutil.which(MPV_PATH) or MPV_PATH)
    if not (os.path.isabs(mpv_bin) or shutil.which(mpv_bin)):
        print(f"mpv not found on PATH (MPV_PATH={MPV_PATH}).")
        return False

    # If program socket already responds, we’re good on the main instance.
    if _mpv_ipc_ready_socket(MPV_SOCKET):
        prog_ready = True
    else:
        # Program (fullscreen) instance
        _ensure_dir_for(MPV_SOCKET)
        log_prog = "/tmp/karel_mpv_prog.log"
        base_prog = [
            mpv_bin,
            f"--input-ipc-server={MPV_SOCKET}",
            "--idle=yes",
            "--force-window=immediate",
            f"--log-file={log_prog}",
        ]
        sec = _detect_secondary_monitor_name()
        attempt_cmds = []
        if sec:
            attempt_cmds.append(base_prog + ["--fs", f"--fs-screen={sec}"])
        attempt_cmds.append(base_prog + ["--fs"])
        attempt_cmds.append(base_prog)

        prog_ready = False
        for cmd in attempt_cmds:
            try:
                _mpv_proc = subprocess.Popen(cmd + (shlex.split(MPV_ARGS) if MPV_ARGS else []),
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Failed to start mpv (program): {e}")
                _mpv_proc = None
                continue

            for _ in range(50):  # up to ~5s
                if _mpv_ipc_ready_socket(MPV_SOCKET):
                    prog_ready = True
                    break
                time.sleep(0.1)

            if prog_ready:
                break

            try:
                if _mpv_proc and _mpv_proc.poll() is None:
                    _mpv_proc.terminate()
                    _mpv_proc.wait(timeout=0.8)
            except Exception:
                pass
            _mpv_proc = None

        if not prog_ready:
            print(f"mpv (program) IPC not ready; check log at {log_prog}")

    # Optionally start Preview instance (doesn't block main readiness)
    if MPV_PREVIEW_ENABLE and MPV_PREVIEW_SOCKET:
        if not _mpv_ipc_ready_socket(MPV_PREVIEW_SOCKET):
            _ensure_dir_for(MPV_PREVIEW_SOCKET)
            log_prev = "/tmp/karel_mpv_prev.log"
            prev_cmd = [
                mpv_bin,
                f"--input-ipc-server={MPV_PREVIEW_SOCKET}",
                "--idle=yes",
                "--force-window=immediate",
                f"--log-file={log_prev}",
            ] + (shlex.split(MPV_PREVIEW_ARGS) if MPV_PREVIEW_ARGS else [])

            try:
                subprocess.Popen(prev_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Failed to start mpv (preview): {e}")
            else:
                # Give it a moment to come up (don’t block too long)
                for _ in range(30):  # up to ~3s
                    if _mpv_ipc_ready_socket(MPV_PREVIEW_SOCKET):
                        break
                    time.sleep(0.1)

        # Optionally preload the same video in preview (only if main was preloaded elsewhere)
        if VIDEO_FILE and os.path.isfile(VIDEO_FILE):
            # Only load if preview isn’t already on that file (best-effort)
            mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["loadfile", VIDEO_FILE, "replace"]})
            time.sleep(0.05)
            mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["set_property", "pause", True]})
            mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["set_property", "time-pos", 0]})

    return bool(prog_ready)

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
        self.mpv_play_delay_ms = int(MPV_PLAY_DELAY_MS)  # runtime-editable

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

        # Controls: MPV play delay (ms)
        self.controls_frame = tk.Frame(root)
        self.controls_frame.pack(fill='x', padx=10, pady=(0, 10))
        tk.Label(self.controls_frame, text='Play Delay (ms):', width=16, anchor='w').pack(side='left')
        self.delay_value_lbl = tk.Label(self.controls_frame, text=str(self.mpv_play_delay_ms), width=8, anchor='w')
        self.delay_value_lbl.pack(side='left')
        tk.Button(self.controls_frame, text='Set…', command=self.open_delay_prompt).pack(side='left', padx=(6, 0))
        # Default focus to canvas for keyboard controls
        self.root.after(0, self.canvas.focus_set)

        self.rects = []
        self.texts = []
        self.draw_rects()
        self.update_status_labels()

        for key in ['1', '2', '3', '4', '0', 'p', 'P']:
            self.root.bind(key, self.on_key)
        self.root.bind('<space>', self.on_key)
        # Frame stepping bindings
        self.root.bind('<Left>', self.on_key)
        self.root.bind('<Right>', self.on_key)

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
        self.start_mpv_sync()   # <<< start preview sync loop


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
            text="Keys: 1..4 CUE, Space CUT, 0 clear, P play-on-cut, ←/→ pause+±10 frames",
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

        # If requested, start mpv playback on this trigger (with optional delay)
        if self.play_on_next_trigger:
            delay = max(0, int(self.mpv_play_delay_ms))
            if delay > 0:
                try:
                    self.root.after(delay, mpv_play)
                except Exception:
                    # Fallback to immediate play if scheduling fails
                    mpv_play()
            else:
                mpv_play()
            self.play_on_next_trigger = False

            # Tighten sync immediately on trigger (optional)
            if MPV_PREVIEW_ENABLE and MPV_PREVIEW_SOCKET:
                t = mpv_get(MPV_SOCKET, "time-pos", None)
                if t is not None:
                    mpv_set(MPV_PREVIEW_SOCKET, "time-pos", t)

        self.update_display()

    def open_delay_prompt(self):
        try:
            val = simpledialog.askinteger(
                title='Set Play Delay',
                prompt='Enter play delay in milliseconds:',
                initialvalue=int(self.mpv_play_delay_ms),
                minvalue=1,
                parent=self.root
            )
        except Exception:
            val = None
        if val is None:
            # Cancelled
            self.canvas.focus_set()
            return
        try:
            val = int(val)
            if val < 1:
                # Enforce strictly positive values
                val = 1
        except Exception:
            return
        # Apply and persist
        self.mpv_play_delay_ms = val
        if hasattr(self, 'delay_value_lbl'):
            self.delay_value_lbl.config(text=str(val))
        try:
            save_config_value("MPV_PLAY_DELAY_MS", val)
        except Exception:
            pass
        try:
            save_env_value("MPV_PLAY_DELAY_MS", str(val))
        except Exception:
            pass
        self.canvas.focus_set()

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
        elif event.keysym in ['Left', 'Right']:
            # Pause and step ±10 frames
            try:
                # Ensure paused
                mpv_set(MPV_SOCKET, "pause", True)
                # Step frames
                cmd = "frame-back-step" if event.keysym == 'Left' else "frame-step"
                for _ in range(10):
                    mpv_send({"command": [cmd]})
                # Sync preview position while paused
                if MPV_PREVIEW_ENABLE and MPV_PREVIEW_SOCKET:
                    mpv_set(MPV_PREVIEW_SOCKET, "pause", True)
                    t = mpv_get(MPV_SOCKET, "time-pos", None)
                    if t is not None:
                        mpv_set(MPV_PREVIEW_SOCKET, "time-pos", t)
            except Exception as e:
                print(f"MPV frame step error: {e}")
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
                    # Optional delay before triggering, configurable via env/config
                    try:
                        d = max(0, int(ARDUINO_TRIGGER_DELAY_MS))
                    except Exception:
                        d = 200
                    if d:
                        time.sleep(d / 1000.0)
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
    def start_mpv_sync(self):
        self._sync_job = None
        if MPV_SYNC_ENABLE:
            self._mpv_sync_tick()

    def _mpv_sync_tick(self):
        try:
            # Only run if program socket is alive
            prog_pause = mpv_get(MPV_SOCKET, "pause", None)
            if prog_pause is None:
                # program not up; try again later
                pass
            else:
                # Mirror file path
                prog_path = mpv_get(MPV_SOCKET, "path", "")
                if MPV_PREVIEW_ENABLE and MPV_PREVIEW_SOCKET:
                    prev_path = mpv_get(MPV_PREVIEW_SOCKET, "path", "")
                    if prog_path and prog_path != prev_path:
                        mpv_send_to(MPV_PREVIEW_SOCKET, {"command": ["loadfile", prog_path, "replace"]})
                        # ensure muted + paused state mirrors right away
                        mpv_set(MPV_PREVIEW_SOCKET, "pause", prog_pause)
                        mpv_set(MPV_PREVIEW_SOCKET, "mute", True)

                    # Mirror pause + speed
                    prev_pause = mpv_get(MPV_PREVIEW_SOCKET, "pause", None)
                    if prev_pause is not None and prev_pause != prog_pause:
                        mpv_set(MPV_PREVIEW_SOCKET, "pause", prog_pause)

                    prog_speed = mpv_get(MPV_SOCKET, "speed", 1.0)
                    prev_speed = mpv_get(MPV_PREVIEW_SOCKET, "speed", 1.0)
                    if abs(float(prev_speed) - float(prog_speed)) > 1e-3:
                        mpv_set(MPV_PREVIEW_SOCKET, "speed", prog_speed)

                    # Time sync (nudge preview when drift exceeds threshold)
                    prog_t = mpv_get(MPV_SOCKET, "time-pos", None)
                    prev_t = mpv_get(MPV_PREVIEW_SOCKET, "time-pos", None)
                    if prog_t is not None and prev_t is not None:
                        try:
                            drift = float(prog_t) - float(prev_t)
                            if abs(drift) > MPV_SYNC_DRIFT_SEC:
                                mpv_set(MPV_PREVIEW_SOCKET, "time-pos", prog_t)
                        except Exception:
                            pass
        finally:
            # schedule next tick
            self._sync_job = self.root.after(MPV_SYNC_INTERVAL_MS, self._mpv_sync_tick)


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
