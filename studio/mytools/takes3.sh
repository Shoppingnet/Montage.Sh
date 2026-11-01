#!/bin/bash
# takes3.sh REF -> t1..t3 wav (tightened) + scores
cd /home/claude/work/$1
for i in 1 2 3; do
  for k in 1 2 3; do
    [ -s t$i.pcm ] && break
    GK=/home/claude/.gk python3 /home/claude/kit/tts.py script.txt t$i Laomedeia >/dev/null 2>tts_err.txt || GK=/home/claude/.gk2 python3 /home/claude/kit/tts.py script.txt t$i Laomedeia >/dev/null 2>>tts_err.txt || sleep 20
  done
  [ -s t$i.pcm ] || echo "t$i FAILED"
  [ -s t$i.pcm ] && [ ! -s t${i}t.wav ] && cp t$i.pcm t$i.wav && python3 /home/claude/toolsB/tighten.py t$i.wav t${i}t.wav 0.28
done
python3 /home/claude/tools/score.py script.txt $(ls t[123]t.wav) 2>&1 | grep score
