# usage: python3 build.py <workdir>   (workdir has src/*.mp4, plan.json, voice.wav, gender.txt = F|M)
import os,json,subprocess,os,sys
W=sys.argv[1]; os.chdir(W)
P=json.load(open('plan.json')); os.makedirs('seg',exist_ok=True)
for i,(v,a,b,f) in enumerate(P):
    d=b-a; src=f'src/{v}.mp4'
    import re as _re
    dl=_re.search(r'\|dl:([\d.]+),([\d.]+),([\d.]+),([\d.]+)',f); f=_re.sub(r'\|dl:[\d.,]+','',f)
    pre=''
    if dl:
        sw,sh=[int(z) for z in subprocess.run(["ffprobe","-v","error","-select_streams","v","-show_entries","stream=width,height","-of","csv=p=0",src],capture_output=True,text=True).stdout.split(',')[:2]]
        x0,y0,x1,y1=[float(z) for z in dl.groups()]
        pre=f"delogo=x={max(1,int(x0*sw))}:y={max(1,int(y0*sh))}:w={int((x1-x0)*sw)}:h={int((y1-y0)*sh)},"
    m=_re.search(r'\|s([\d.]+)',f); slow=1.5 if f.endswith('|slow') else (float(m.group(1)) if m else 0); mx=_re.search(r'\|x([\d.]+)',f); X=float(mx.group(1)) if mx else 0.5; f=_re.sub(r'\|(slow|s[\d.]+|x[\d.]+)','',f)
    if f=="":
        fc=f"[0:v]{pre}scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-1080)*{X}:0,unsharp=5:5:0.8,setsar=1,fps=30[o]"
    else:
        # f like "band:0.00-0.68" keep that vertical band, letterboxed on blurred bg
        y0,y1=[float(x) for x in f.split(':')[1].split('-')]
        band=f"crop=iw:ih*{y1-y0:.3f}:0:ih*{y0:.3f}"
        fc=(f"[0:v]{pre}{band},scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920:(iw-1080)*{X}:0,unsharp=5:5:0.6,setsar=1,fps=30[o]")
    if slow: fc=fc.replace("fps=30[o]",f"setpts={slow}*PTS,fps=30[o]")
    subprocess.run(["ffmpeg","-v","error","-y","-ss",str(a),"-t",str(d),"-i",src,"-filter_complex",fc,"-map","[o]","-an",
        "-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p",f"seg/{i:02d}.mp4"],check=True)
open('seg/list.txt','w').write("".join(f"file '{i:02d}.mp4'\n" for i in range(len(P))))
subprocess.run(["ffmpeg","-v","error","-y","-f","concat","-safe","0","-i","seg/list.txt","-c","copy","silent.mp4"],check=True)
g=open('gender.txt').read().strip()
html=open('/home/claude/kit/card.html').read().replace('CTA','دوزي الكوموند دابا' if g=='F' else 'دوز الكوموند دابا')
open('card.html','w').write(html)
subprocess.run(["node","-e","const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});await p.goto('file://'+process.cwd()+'/card.html');await p.waitForTimeout(500);await p.screenshot({path:'card.png',omitBackground:true});await b.close()})()"],check=False)
dur=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0","voice.wav"],capture_output=True,text=True).stdout)
T=dur+0.4; cs=max(0,dur-3.0)
out=open('name.txt').read().strip()+'.mp4'
FD="/home/claude/kit/frames/"+os.environ.get("FRAME_STYLE","1")
subprocess.run(["ffmpeg","-v","error","-y","-i","silent.mp4","-i","voice.wav","-loop","1","-i",FD+"/card_"+g+".png","-i",FD+"/badge.png","-i",FD+"/frame.png","-filter_complex",
 f"[0:v]tpad=stop_mode=clone:stop_duration=2[v0];[v0][3:v]overlay=0:0:enable='lt(t,{cs:.2f})'[v];[2:v]format=rgba,fade=in:st={cs:.2f}:d=0.25:alpha=1[c];[v][c]overlay=0:0:enable='gte(t,{cs:.2f})':shortest=1[vf];[vf][4:v]overlay=0:0[vo];[1:a]apad=pad_dur=0.5,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
 "-map","[vo]","-map","[a]","-t",f"{T:.2f}","-r","30","-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-ar","48000","-movflags","+faststart",out],check=True)
subprocess.run(["ffmpeg","-v","error","-y","-i",out,"-vf","fps=1,scale=180:-1,drawtext=text='%{pts\\:hms}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black,tile=9x5","-frames:v","1","final_sheet.jpg"],check=True)
print("OK",out,round(T,1))
