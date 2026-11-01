# usage: python3 reframe.py in.mp4 out.mp4 STYLE(1-10) [frame|frame+badge]
# Old videos already have their own order card at the end -> default adds frame + phone badge, NO end card so nothing repeats.
import sys,subprocess
i,o,s=sys.argv[1:4]; mode=sys.argv[4] if len(sys.argv)>4 else "frame+badge"
FD=f"/home/claude/kit/frames/{s}"
ins=["-i",i,"-loop","1","-i",f"{FD}/frame.png"]
fc="[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v0];[v0][1:v]overlay=0:0:shortest=1"
if mode=="frame+badge":
    ins+=["-loop","1","-i",f"{FD}/badge.png"]; fc+="[v1];[v1][2:v]overlay=0:0:shortest=1"
fc+="[v]"
subprocess.run(["ffmpeg","-v","error","-y",*ins,"-filter_complex",fc,"-map","[v]","-map","0:a?","-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p","-c:a","copy","-movflags","+faststart",o],check=True)
print("OK",o)
