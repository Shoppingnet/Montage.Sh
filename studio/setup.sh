#!/bin/bash
# Installs the Shopping Net montage kit into /home/claude (same paths the tools expect).
set -e
S=$(cd "$(dirname "$0")" && pwd)
mkdir -p /home/claude/work
cp -r "$S/kit" "$S/mytools" "$S/toolsB" /home/claude/
cp "$S/dl.py" "$S/ready.json" "$S/split.json" /home/claude/
pip install -q --break-system-packages faster-whisper yt-dlp curl_cffi 2>/dev/null || true
which ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg)
echo "kit installed. Now save your Gemini key:  umask 077; printf '%s' 'KEY' > /home/claude/.gk"
