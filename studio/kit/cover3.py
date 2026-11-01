# cover3.py — one strong shot + one short hook line, no phone badge (Top 02/11)
# usage: python3 cover3.py video_or_image STYLE out.jpg T "hook line" [small line]
import sys,subprocess,os,html,tempfile
v,s,out,t,hook=sys.argv[1:6]; small=sys.argv[6] if len(sys.argv)>6 else ''
tmp=tempfile.mkdtemp()
if v.lower().endswith(('.png','.jpg','.jpeg','.webp')):
    subprocess.run(["ffmpeg","-v","error","-y","-i",v,f"{tmp}/i.png"],check=True)
else:
    src=os.path.join(os.path.dirname(os.path.abspath(v)),'silent.mp4'); raw=os.path.exists(src)
    crop='' if raw else 'crop=iw*0.86:ih*0.80:iw*0.07:ih*0.12,'
    subprocess.run(["ffmpeg","-v","error","-y","-ss",t,"-i",src if raw else v,"-frames:v","1","-vf",crop+"scale=1080:-2",f"{tmp}/i.png"],check=True)
P={1:('#FFF3C4','#D9AE52','#8C6420'),2:('#FFF3C4','#D9AE52','#8C6420'),3:('#FFF0C9','#D9AE52','#8C6420'),4:('#FFF3C4','#D9AE52','#8C6420'),5:('#FFF3C4','#D9AE52','#8C6420'),6:('#E8C66A','#B8862B','#7a5418'),7:('#FFFFFF','#C9CED6','#7d848f'),8:('#FBE3D6','#E3A587','#9c5f48'),9:('#F6E9C8','#D8BE86','#8f7444'),10:('#FAD9B5','#C98A4B','#7a4a1f')}
a,m,dk=P[int(s)]; HL={1:'#FCD714',2:'#FF7A3D',3:'#FF4D6D',4:'#3DDC84',5:'#C77DFF',6:'#FFD23F',7:'#4CC9F0',8:'#FF8FA3',9:'#2EC4B6',10:'#FFB347'}[int(s)]; FD=f"/home/claude/kit/frames/{s}"
n=len(hook); fs=128 if n<=14 else 112 if n<=20 else 96 if n<=28 else 82
page=f'''<html><head><meta charset="utf-8"><style>
@font-face{{font-family:Marhey;src:url('file:///home/claude/kit/fonts/x3d8ck7Laq-T7wl7mqfVrEe9sDvtBSx3O2c.ttf')}}
body{{margin:0;width:1080px;height:1920px;position:relative;overflow:hidden;direction:rtl;background:#000}}
.im{{position:absolute;inset:0;background:url('file://{tmp}/i.png') center/cover}}
.sh{{position:absolute;left:0;right:0;top:300px;height:520px;background:linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,.55) 30%,rgba(0,0,0,.55) 70%,rgba(0,0,0,0))}}
.box{{position:absolute;left:70px;right:70px;top:430px;text-align:center}}
.hk{{font-family:Marhey;font-size:{fs}px;line-height:1.18;color:#fff;-webkit-text-stroke:3px rgba(0,0,0,.5);paint-order:stroke fill;filter:drop-shadow(0 6px 5px rgba(0,0,0,.95))}}
.hk b{{font-weight:inherit;color:#111;-webkit-text-stroke:0;background:{HL};padding:0 22px 10px;border-radius:22px;box-decoration-break:clone;-webkit-box-decoration-break:clone}}
.sm{{margin-top:22px;font-family:Marhey;font-size:46px;color:{a};filter:drop-shadow(0 3px 3px rgba(0,0,0,.95))}}
.fr{{position:absolute;inset:0;background:url('file://{FD}/frame.png')}}
</style></head><body><div class="im"></div><div class="sh"></div>
<div class="box"><div class="hk">{html.escape(hook).replace('[','<b>').replace(']','</b>')}</div>{f'<div class="sm">{html.escape(small)}</div>' if small else ''}</div>
<div class="fr"></div></body></html>'''
open(f"{tmp}/c.html","w").write(page)
subprocess.run(["node","-e",f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage({{viewport:{{width:1080,height:1920}}}});await p.goto('file://{tmp}/c.html');await p.waitForTimeout(700);await p.screenshot({{path:'{tmp}/c.png'}});await b.close()}})()"],check=True)
subprocess.run(["ffmpeg","-v","error","-y","-i",f"{tmp}/c.png","-q:v","2",out],check=True)
print('OK',out)
