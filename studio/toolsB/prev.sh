#!/bin/bash
# move old version into prev_v1 (keeps src, photo, name, gender, shB sheets)
cd "$1"; [ -d prev_v1 ] && { echo "prev_v1 exists"; exit 0; }
mkdir prev_v1
for f in *; do case "$f" in src|prev_v1|photo.*|name.txt|gender.txt|shB_*) ;; seg|silent.mp4|t[0-9].pcm|t[0-9].wav) rm -rf "$f";; *) mv "$f" prev_v1/;; esac; done
ls; ls prev_v1
