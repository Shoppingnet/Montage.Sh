#!/bin/bash
# gen3.sh REF [N=2] -> tN.wav ; .gk first, then .gk2; no retry loop
cd /home/claude/work/$1; N=${2:-2}
for i in $(seq 1 $N); do
  [ -f t$i.wav ] && continue
  rm -f t$i.pcm
  GK=/home/claude/.gk python3 /home/claude/kit/tts.py script.txt t$i Laomedeia >/dev/null 2>&1 || GK=/home/claude/.gk2 python3 /home/claude/kit/tts.py script.txt t$i Laomedeia >/dev/null 2>&1
  [ -f t$i.pcm ] && ffmpeg -v error -y -f s16le -ar 24000 -ac 1 -i t$i.pcm t$i.wav || { echo "t$i FAILED (429?)"; break; }
done
ls t*.wav
