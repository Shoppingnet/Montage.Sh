#!/bin/bash
# sheets.sh REF [fps]  -> /home/claude/work/REF/shA_<clip>_<k>.jpg, 30 frames each (10x3) at given fps (default 1)
R=$1; F=${2:-1}; cd /home/claude/work/$R
for f in src/*.mp4; do b=$(basename $f .mp4)
 d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $f); n=$(python3 -c "import math;print(math.ceil($d*$F/30))")
 for k in $(seq 0 $((n-1))); do s=$(python3 -c "print($k*30/$F)")
  bash /home/claude/mytools/waitff.sh
  ffmpeg -v error -y -ss $s -t $(python3 -c "print(30/$F)") -i $f -vf "fps=$F,scale=160:-1,drawtext=text='%{pts\:hms\:$s}':x=3:y=3:fontsize=15:fontcolor=yellow:box=1:boxcolor=black,tile=10x3" -frames:v 1 shA_${b}_$k.jpg
 done; done; ls shA_*
