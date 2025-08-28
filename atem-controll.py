import time
import PyATEMMax

def on_press(key):
    if str(key).replace("'","") == '0':
        print('pressed 0')

listener = Listener(on_press=on_press)
listener.start()

ATEM_IP = "172.17.0.79"
INPUT_NUMBER = 3           # HDMI input to switch to (1–4)
# ATEM_PORT = 4242

PRG = 1
CUE = 1

switcher = PyATEMMax.ATEMMax()

# Connect
switcher.connect(ATEM_IP)
switcher.waitForConnection()

while True:
    if CUE != PRG:
        PRG = CUE
        switcher.setProgramInputVideoSource(0, PRG)
    
    time.sleep(0.2)

    
