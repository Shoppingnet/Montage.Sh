#!/bin/bash
# ttsq.sh REF... : waits for TTS quota, then makes 3 takes each
for R in "$@"; do
 cd /home/claude/work/$R
 for i in 1 2 3; do
  until [ -s t$i.pcm ]; do
    GK=/home/claude/.gk python3 /home/claude/kit/tts.py script.txt t$i Laomedeia >/dev/null 2>/dev/null || GK=/home/claude/.gk2 python3 /home/claude/kit/tts.py script.txt t$i Laomedeia >/dev/null 2>/dev/null || sleep 120
  done
  cp t$i.pcm t$i.wav; python3 /home/claude/toolsB/tighten.py t$i.wav t${i}t.wav 0.28
 done
 python3 /home/claude/tools/score.py script.txt t1t.wav t2t.wav t3t.wav 2>&1 | grep score > scores.txt
 echo "$R done"
done
