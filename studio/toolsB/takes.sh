#!/bin/bash
# usage: takes.sh <workdir> <from> <to>  -> takeN.wav + score
cd "$1"
for i in $(seq $2 $3); do
  [ -f take$i.pcm ] || GK=/home/claude/.gk2 python3 /home/claude/kit/tts.py script.txt take$i Laomedeia >/dev/null 2>&1 || GK=/home/claude/.gk python3 /home/claude/kit/tts.py script.txt take$i Laomedeia >/dev/null 2>&1 || echo "take$i FAILED"
  [ -f take$i.pcm ] && cp take$i.pcm take$i.wav
done
python3 /home/claude/tools/score.py script.txt $(ls take*.wav) 2>&1 | grep score
