# usage: python3 cover.py video.mp4 "اسم المنتج" STYLE out.jpg [seconds]
# 1080x1920 cover for Reels/Stories; name + badge kept inside the centre 1080x1350 zone so the 4:5 feed crop still shows them.
import sys,subprocess,os,json,html,tempfile
v,name,s,out=sys.argv[1:5]; t=sys.argv[5] if len(sys.argv)>5 else None
tmp=tempfile.mkdtemp(); bg=f"{tmp}/bg.png"
clean=os.path.join(os.path.dirname(os.path.abspath(v)),'silent.mp4')
if os.path.exists(clean): v=clean  # frames without badge/frame/card
if t: subprocess.run(["ffmpeg","-v","error","-y","-ss",t,"-i",v,"-frames:v","1","-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",bg],check=True)
else:  # sharpest representative frame from the first 60% of the video
    d=float(json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","json",v]))["format"]["duration"])
    subprocess.run(["ffmpeg","-v","error","-y","-t",f"{d*0.6:.2f}","-i",v,"-vf","thumbnail=90,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920","-frames:v","1",bg],check=True)
P={1:('#0e1f45','#FFF3C4','#D9AE52','#8C6420'),2:('#121212','#FFF3C4','#D9AE52','#8C6420'),3:('#6b1224','#FFF0C9','#D9AE52','#8C6420'),4:('#0d4a3a','#FFF3C4','#D9AE52','#8C6420'),5:('#3b1a5c','#FFF3C4','#D9AE52','#8C6420'),6:('#E6DCC8','#E8C66A','#B8862B','#7a5418'),7:('#15171c','#FFFFFF','#C9CED6','#7d848f'),8:('#3a1f22','#FBE3D6','#E3A587','#9c5f48'),9:('#0b3a44','#F6E9C8','#D8BE86','#8f7444'),10:('#3b2416','#FAD9B5','#C98A4B','#7a4a1f')}
b,a,m,dk=P[int(s)]; FD=f"/home/claude/kit/frames/{s}"
n=len(name); fs=104 if n<=16 else 92 if n<=24 else 80 if n<=32 else 68
page=f'''<html><head><meta charset="utf-8"><style>
@font-face{{font-family:Marhey;src:url('file:///home/claude/kit/fonts/x3d8ck7Laq-T7wl7mqfVrEe9sDvtBSx3O2c.ttf')}}
body{{margin:0;width:1080px;height:1920px;position:relative;overflow:hidden;direction:rtl}}
.bg{{position:absolute;inset:0;background:url('file://{bg}') center/cover}}
.sh{{position:absolute;left:0;right:0;top:980px;height:940px;background:linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,.55) 45%,rgba(0,0,0,.75))}}
.fr{{position:absolute;inset:0;background:url('file://{FD}/frame.png')}}
.bd{{position:absolute;inset:0;background:url('file://{FD}/badge.png') 0 100px no-repeat}}
.box{{position:absolute;left:70px;right:70px;top:1230px;text-align:center}}
.nm{{font-family:Marhey;font-size:{fs}px;line-height:1.25;background:linear-gradient(180deg,{a},{m} 45%,{dk} 72%,{a});-webkit-background-clip:text;color:transparent;filter:drop-shadow(0 4px 3px rgba(0,0,0,.95)) drop-shadow(0 0 14px rgba(0,0,0,.6))}}
.ln{{width:260px;height:4px;margin:18px auto 0;background:linear-gradient(90deg,transparent,{m},transparent)}}
.cod{{display:inline-block;margin-top:20px;font-family:Marhey;font-size:44px;color:#111;padding:8px 40px 14px;border-radius:999px;background:linear-gradient(135deg,{a},{m} 50%,{a});box-shadow:0 6px 16px rgba(0,0,0,.4)}}
</style></head><body><div class="bg"></div><div class="sh"></div><div class="bd"></div><div class="fr"></div>
<div class="box"><div class="nm">{html.escape(name)}</div><div class="ln"></div><div class="cod">الخلاص عند الاستلام</div></div></body></html>'''
open(f"{tmp}/c.html","w").write(page)
subprocess.run(["node","-e",f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage({{viewport:{{width:1080,height:1920}}}});await p.goto('file://{tmp}/c.html');await p.waitForTimeout(600);await p.screenshot({{path:'{tmp}/c.png'}});await b.close()}})()"],check=True)
subprocess.run(["ffmpeg","-v","error","-y","-i",f"{tmp}/c.png","-q:v","2",out],check=True)
print("OK",out)
