#!/bin/bash
# cuts2.sh REF clip1 clip2 ...
R=$1; shift; cd /home/claude/work/$R
for c in "$@"; do f=src/$c.mp4; bash /home/claude/mytools/waitff.sh; echo -n "$c: "; ffmpeg -v info -i $f -vf "scale=160:-1,scdet=t=8:s=0" -an -f null - 2>&1 | grep -o 'lavfi.scd.time: [0-9.]*' | awk '{printf "%.2f ",$2}'; echo; done
