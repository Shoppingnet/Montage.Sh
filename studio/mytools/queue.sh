#!/bin/bash
# queue.sh "REF:STYLE" ...  -> builds sequentially, waiting for ffmpeg idle before each
for x in "$@"; do R=${x%%:*}; S=${x##*:}
  bash /home/claude/mytools/waitff.sh
  cd /home/claude/kit && FRAME_STYLE=$S python3 /home/claude/mytools/build3.py /home/claude/work/$R 2>&1 | tail -1
done
