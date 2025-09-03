import socket
import json
import os
import time
import sys
import termios
import tty
import select

MPV_SOCKET = "/tmp/mpvsocket"
LIVE_INPUT = "./test1.mp4"
VIDEO_FILE = "./test2.mp4"

def send_command(command):
    if not os.path.exists(MPV_SOCKET):
        print("Error: mpv socket not found!")
        return
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(MPV_SOCKET)
        client.send((json.dumps(command) + '\n').encode('utf-8'))
        response = client.recv(4096)
        client.close()
        return json.loads(response.decode('utf-8'))
    except Exception as e:
        print("Socket error:", e)

def key_pressed():
    dr, dw, de = select.select([sys.stdin], [], [], 0)
    return dr != []

def getch():
    return sys.stdin.read(1)

def toggle_pause():
    return send_command({"command": ["cycle", "pause"]})

def restart_file():
    return send_command({"command": ["seek", 0, "absolute", "exact"]})

def switch_to_video_file():
    print("Switching to video file (blend A)...")
    return send_command({
        "command": ["set_property", "vf", "lavfi=[vid1]scale=1280:720[main];[vid0]scale=1280:720[live];[main][live]blend=all_expr='A'[out]"]
    })

def switch_to_live_input():
    print("Switching to live input (blend B)...")
    return send_command({
        "command": ["set_property", "vf", "lavfi=[vid1]scale=1280:720[main];[vid0]scale=1280:720[live];[main][live]blend=all_expr='B'[out]"]
    })

def main():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    print("\nControls:")
    print("  [1] Show LIVE input")
    print("  [2] Show VIDEO file")
    print("  [SPACE] Play/Pause video file")
    print("  [0] Restart video file")
    print("  [q] Quit\n")

    try:
        while True:
            if key_pressed():
                ch = getch()

                if ch == '1':
                    switch_to_live_input()
                elif ch == '2':
                    switch_to_video_file()
                elif ch == ' ':
                    toggle_pause()
                elif ch == '0':
                    restart_file()
                elif ch.lower() == 'q':
                    print("Quitting...")
                    break

            time.sleep(0.1)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()
"""
mpv IPC controller: toggle between live input and video file

Description
- Talks to an mpv instance via its UNIX socket (MPV_SOCKET) and applies
  filter graphs to switch/blend between two inputs.

Requirements
- mpv started with: mpv --input-ipc-server=/tmp/mpvsocket --idle=yes \\
    --lavfi-complex='[vid1]scale=1280:720[main];[vid0]scale=1280:720[live];[main][live]blend=all_expr=A[out]'

Controls
- 1: show LIVE input (blend B)
- 2: show VIDEO file (blend A)
- SPACE: play/pause video file
- 0: restart video file
- q: quit

Usage
- python3 karel/switch_video.py
  Ensure MPV_SOCKET points to the mpv IPC socket.
"""
