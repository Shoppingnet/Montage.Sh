#!/bin/bash
# cuts.sh REF -> scene cut times per clip
cd /home/claude/work/$1
for f in src/*.mp4; do bash /home/claude/mytools/waitff.sh; echo -n "$(basename $f .mp4): "; ffmpeg -v info -i $f -vf "scale=160:-1,scdet=t=10:s=0" -an -f null - 2>&1 | grep -o 'lavfi.scd.time: [0-9.]*' | awk '{printf "%.2f ",$2}'; echo; done
