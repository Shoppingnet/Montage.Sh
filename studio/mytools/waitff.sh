#!/bin/bash
# wait until no ffmpeg running (shared CPU)
while pgrep -x ffmpeg >/dev/null; do sleep 3; done
