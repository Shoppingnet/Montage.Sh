# cover2.py — problem/solution thumbnail that matches the ad copy
# usage: python3 cover2.py video.mp4 STYLE out.jpg T_PROBLEM T_SOLUTION "problem headline" "solution line" ["product name"]
# Top half: the problem the customer has without the product (frame at T_PROBLEM) + headline.
# Bottom half: the product solving it (frame at T_SOLUTION) + solution line. Number badge + COD pill.
import sys,subprocess,os,html,tempfile
v,s,out,tp,ts,prob,sol=sys.argv[1:8]; name=sys.argv[8] if len(sys.argv)>8 else ''
tmp=tempfile.mkdtemp()
src=os.path.join(os.path.dirname(os.path.abspath(v)),'silent.mp4')
raw=os.path.exists(src)
if not raw: src=v
# final video carries the frame + badge: crop to the inner picture
crop='' if raw else 'crop=iw*0.86:ih*0.80:iw*0.07:ih*0.12,'
for nm,t in (('p',tp),('s',ts)):
    img=os.environ.get(nm.upper()+'_IMG')
    if img: subprocess.run(['ffmpeg','-v','error','-y','-i',img,'-vf','scale=1080:-2',f'{tmp}/{nm}.png'],check=True); continue
    subprocess.run(["ffmpeg","-v","error","-y","-ss",t,"-i",src,"-frames:v","1","-vf",crop+"scale=1080:-2",f"{tmp}/{nm}.png"],check=True)
P={1:('#0e1f45','#FFF3C4','#D9AE52','#8C6420'),2:('#121212','#FFF3C4','#D9AE52','#8C6420'),3:('#6b1224','#FFF0C9','#D9AE52','#8C6420'),4:('#0d4a3a','#FFF3C4','#D9AE52','#8C6420'),5:('#3b1a5c','#FFF3C4','#D9AE52','#8C6420'),6:('#E6DCC8','#E8C66A','#B8862B','#7a5418'),7:('#15171c','#FFFFFF','#C9CED6','#7d848f'),8:('#3a1f22','#FBE3D6','#E3A587','#9c5f48'),9:('#0b3a44','#F6E9C8','#D8BE86','#8f7444'),10:('#3b2416','#FAD9B5','#C98A4B','#7a4a1f')}
b,a,m,dk=P[int(s)]; FD=f"/home/claude/kit/frames/{s}"
def fs(t,big): n=len(t); return big if n<=14 else int(big*0.86) if n<=20 else int(big*0.74) if n<=28 else int(big*0.62)
page=f'''<html><head><meta charset="utf-8"><style>
@font-face{{font-family:Marhey;src:url('file:///home/claude/kit/fonts/x3d8ck7Laq-T7wl7mqfVrEe9sDvtBSx3O2c.ttf')}}
body{{margin:0;width:1080px;height:1920px;position:relative;overflow:hidden;direction:rtl;background:{b}}}
.pan{{position:absolute;left:0;right:0;overflow:hidden}}
.pan img{{width:100%;height:100%;object-fit:cover;display:block}}
.p{{top:0;height:980px}} .s{{top:990px;height:930px}}
.p::after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.05) 35%,rgba(0,0,0,.72))}}
.s::after{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.0) 40%,rgba(0,0,0,.70))}}
.sep{{position:absolute;left:0;right:0;top:978px;height:14px;background:linear-gradient(90deg,{dk},{a},{m},{a},{dk})}}
.tag{{position:absolute;right:60px;font-family:Marhey;font-size:46px;padding:6px 34px 12px;border-radius:999px;color:#fff;box-shadow:0 6px 16px rgba(0,0,0,.45)}}
.tp{{top:470px;background:#c0262d}} .ts{{top:1040px;background:#1f7a4a}}
.hd{{position:absolute;left:60px;right:60px;text-align:center;font-family:Marhey;line-height:1.2;color:#fff;
 -webkit-text-stroke:3px rgba(0,0,0,.55);paint-order:stroke fill;filter:drop-shadow(0 5px 4px rgba(0,0,0,.9))}}
.hp{{bottom:{1920-940}px;font-size:{fs(prob,104)}px}}
.hs{{bottom:285px;font-size:{fs(sol,88)}px;color:{a}}}
.nm{{position:absolute;left:60px;right:60px;bottom:215px;text-align:center;font-family:Marhey;font-size:36px;color:#fff;opacity:.92;filter:drop-shadow(0 3px 3px rgba(0,0,0,.9))}}
.cod{{position:absolute;left:0;right:0;bottom:95px;text-align:center}}
.cod span{{display:inline-block;font-family:Marhey;font-size:48px;color:#111;padding:8px 44px 14px;border-radius:999px;background:linear-gradient(135deg,{a},{m} 50%,{a});box-shadow:0 6px 16px rgba(0,0,0,.45)}}
.bd{{position:absolute;inset:0;background:url('file://{FD}/badge.png') 0 100px no-repeat}}
.fr{{position:absolute;inset:0;background:url('file://{FD}/frame.png')}}
</style></head><body>
<div class="pan p"><img src="file://{tmp}/p.png"></div><div class="pan s"><img src="file://{tmp}/s.png"></div><div class="sep"></div>
<div class="tag tp">المشكل</div><div class="tag ts">الحل</div>
<div class="hd hp">{html.escape(prob)}</div><div class="hd hs">{html.escape(sol)}</div>
{f'<div class="nm">{html.escape(name)}</div>' if name else ''}
<div class="cod"><span>الخلاص عند الاستلام</span></div>
<div class="bd"></div><div class="fr"></div></body></html>'''
open(f"{tmp}/c.html","w").write(page)
subprocess.run(["node","-e",f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();const p=await b.newPage({{viewport:{{width:1080,height:1920}}}});await p.goto('file://{tmp}/c.html');await p.waitForTimeout(700);await p.screenshot({{path:'{tmp}/c.png'}});await b.close()}})()"],check=True)
subprocess.run(["ffmpeg","-v","error","-y","-i",f"{tmp}/c.png","-q:v","2",out],check=True)
print('OK',out)
