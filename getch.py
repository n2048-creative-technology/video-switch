import socket

ATEM_IP = "172.17.0.79"
INPUT_NUMBER = 3           # HDMI input to switch to (1–4)
ATEM_PORT = 4242

def get_current_program_input(host=ATEM_IP, port=ATEM_PORT, timeout=5):
    """
    Connects to the ATEM UDP status port, waits for one packet,
    parses the program input, returns it.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.bind(('', port))  # bind to local port to receive ATEM UDP packets

    try:
        data, addr = sock.recvfrom(2048)  # wait for one packet
    except socket.timeout:
        print("Timeout waiting for ATEM packet")
        return None
    finally:
        sock.close()

    # Parse the packet data to extract current program input
    program_input = parse_atem_packet(data)
    return program_input

def parse_atem_packet(data):
    # Basic example: guess the program input at byte offset 20 (change if needed)
    if len(data) > 20:
        return data[20]
    return None


if __name__ == "__main__":
    current_input = get_current_program_input()
    if current_input is not None:
        print(f"Current active program input: {current_input}")
    else:
        print("Failed to retrieve program input")
"""
ATEM UDP status probe

Description
- Listens for a single UDP status packet from an ATEM and extracts the
  current Program input using a simple, example parser.

Usage
- python3 karel/getch.py
- Adjust ATEM_IP/ATEM_PORT as needed.

Caveats
- Packet layout may differ across models/firmware; the parse_atem_packet()
  offset is illustrative and may need adjustment.
"""
