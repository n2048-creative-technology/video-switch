#!/bin/bash

# Check if arp-scan is installed
if ! command -v arp-scan &> /dev/null; then
    echo "Please install arp-scan first:"
    echo "  sudo apt update && sudo apt install arp-scan"
    exit 1
fi

# Detect your active network interface automatically
INTERFACE=$(ip route | grep '^default' | awk '{print $5}')

if [ -z "$INTERFACE" ]; then
    echo "Could not detect active network interface."
    exit 1
fi

echo "Scanning network on interface: $INTERFACE ..."

# Run arp-scan on the local subnet
sudo arp-scan --interface=$INTERFACE --localnet | grep -i "Blackmagic"
