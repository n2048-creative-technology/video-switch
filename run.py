#!/usr/bin/env python3

import tkinter as tk
import time
import PyATEMMax
import serial

ATEM_IP = "172.17.0.79"

ARDUINO_PORT = "/dev/ttyUSB0"   # Change to your Arduino port, e.g. "/dev/ttyUSB0" on Linux/Mac
BAUD_RATE = 9600

# Connect to ATEM Mini Pro
switcher = PyATEMMax.ATEMMax()
switcher.connect(ATEM_IP)
# switcher.waitForConnection()

if switcher.connected:
    switcher.setAudioMixerMasterVolume(0)


# Connect to Arduino
try:
    ser = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=0.1)
    print(f"Connected to Arduino on {ARDUINO_PORT}")
except Exception as e:
    print(f"Could not connect to Arduino: {e}")
    ser = None

class ChannelSwitcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Channel Switcher")

        self.PRG = 1
        self.CUE = 1

        # Canvas for rectangles
        self.canvas = tk.Canvas(root, width=600, height=150, bg='lightgrey')
        self.canvas.pack(padx=10, pady=10)

        # Store rect IDs so we can update them
        self.rects = []
        self.texts = []

        self.draw_rects()

        # Bind keys
        for key in ['1', '2', '3', '4', '0']:
            self.root.bind(key, self.on_key)
        self.root.bind('<space>', self.on_key)  # spacebar for cut

        # Start Arduino polling
        if ser:
            self.poll_serial()

    def draw_rects(self):
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
        self.PRG = self.CUE
        if switcher.connected:
            time.sleep(0.05)
            switcher.execCutME(0);
            switcher.setPreviewInputVideoSource(0, self.CUE)
            switcher.setProgramInputVideoSource(0, self.PRG) # not needed
            time.sleep(0.2)
        self.update_display()

    def on_key(self, event):
        if event.char in ['1', '2', '3', '4']:
            self.CUE = int(event.char)
            if switcher.connected:
                switcher.setPreviewInputVideoSource(0, self.CUE)
        if event.char == '0':
            self.CUE = 0
        elif event.keysym == 'space':
           self.trigger()
        
        self.update_display()

    def update_display(self):
        # print(switcher.programInput[0].videoSource.value)
        self.draw_rects()

    def poll_serial(self):        
        """Check Arduino serial for '1' and trigger space action"""
        try:
            if ser.in_waiting:
                data = ser.readline().decode('utf-8').strip()
                if data == "1":
                    time.sleep(0.2)
                    self.trigger()

        except Exception as e:
            print(f"Serial read error: {e}")

        # Schedule next check in 50 ms
        self.root.after(50, self.poll_serial)

def main():
    if switcher.connected:
        switcher.setProgramInputVideoSource(0, 1)
    root = tk.Tk()
    app = ChannelSwitcherApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
