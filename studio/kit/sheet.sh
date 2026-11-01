# usage: bash sheet.sh <clip.mp4> <out.jpg>   contact sheet 1 fps with timestamps
ffmpeg -v error -y -i "$1" -vf "fps=1,scale=180:-1,drawtext=text='%{pts\:hms}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black,tile=9x5" -frames:v 1 "$2"
