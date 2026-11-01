#!/bin/bash
# usage: bw.sh <REF> <FRAME_STYLE>  -> waits until no ffmpeg running, then builds
python3 -c "
import subprocess,time
while subprocess.run(['pgrep','ffmpeg'],capture_output=True).returncode==0: time.sleep(5)
"
cd /home/claude/kit && FRAME_STYLE=$2 python3 /home/claude/mytools/buildC.py /home/claude/work/$1
