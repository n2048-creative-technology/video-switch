#!/bin/bash

MPV_SOCKET="/tmp/mpvsocket"
PYTHON_SCRIPT="switch_video.py"
LIVE_INPUT="./test1.mp4"
VIDEO_FILE="./test2.mp4"
LOGFILE="mpv.log"

# Remove old socket
[ -e "$MPV_SOCKET" ] && rm -f "$MPV_SOCKET"

# Check file
if [ ! -f "$VIDEO_FILE" ]; then
    echo "Error: video file not found: $VIDEO_FILE"
    exit 1
fi

# Start mpv with proper filtergraph
echo "Starting mpv..."

mpv --input-ipc-server="$MPV_SOCKET" \
    --lavfi-complex='[vid1]scale=1280:720[main];[vid0]scale=1280:720[live];[main][live]blend=all_expr=A[out]' \
    --external-files="$LIVE_INPUT" \
    --video-output=out \
    "$VIDEO_FILE" \
    --force-window=yes --idle=yes --no-audio --pause > "$LOGFILE" 2>&1 &

MPV_PID=$!

# Wait until the socket is created
echo -n "Waiting for mpv socket..."
while [ ! -S "$MPV_SOCKET" ]; do
    sleep 0.1
    echo -n "."
done
echo " ready."

# Start Python control script
python3 "$PYTHON_SCRIPT"

# Cleanup
kill $MPV_PID
