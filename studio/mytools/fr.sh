#!/bin/bash
# fr.sh REF clip t1 t2 ... -> /tmp/fr.jpg frames side by side with y-grid lines every 0.1
R=$1; c=$2; shift 2; cd /home/claude/work/$R; i=0; ins=""; n=0
for t in "$@"; do ffmpeg -v error -y -ss $t -i src/$c.mp4 -frames:v 1 -vf "scale=270:480,drawgrid=w=270:h=48:t=1:c=red@0.6,drawtext=text='$t':x=3:y=3:fontsize=18:fontcolor=yellow:box=1" /tmp/f_$n.png; n=$((n+1)); done
ffmpeg -v error -y $(for k in $(seq 0 $((n-1))); do echo -n "-i /tmp/f_$k.png "; done) -filter_complex "hstack=inputs=$n" /tmp/fr.jpg 2>/dev/null || cp /tmp/f_0.png /tmp/fr.jpg
