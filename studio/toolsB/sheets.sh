#!/bin/bash
# usage: sheets.sh <workdir>  -> shB_<clip>.jpg per video clip, 0.5 s steps (1 s if >40 s)
cd "$1"
for f in src/*.mp4; do
  n=$(basename $f .mp4)
  ffprobe -v error -select_streams v -show_entries stream=codec_type -of csv=p=0 $f | grep -q video || { echo "$n: no video"; continue; }
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $f)
  fps=2; awk "BEGIN{exit !($d>40)}" && fps=1
  rows=$(python3 -c "import math;print(math.ceil($d*$fps/10))")
  ffmpeg -v error -y -i $f -vf "fps=$fps,scale=160:-1,drawtext=text='%{pts}':x=3:y=3:fontsize=16:fontcolor=yellow:box=1:boxcolor=black,tile=10x$rows" -frames:v 1 shB_$n.jpg
  echo "$n dur=$d $(ffprobe -v error -select_streams v -show_entries stream=width,height -of csv=p=0 $f)"
done
