# align.py REF  -> uses voice.wav + script.txt (one sentence per line) -> lines.json [[start,end,text],...]
import sys,re,json,subprocess,difflib,numpy as np
from faster_whisper import WhisperModel
D=f"/home/claude/work/{sys.argv[1]}/"
def norm(t):
    t=re.sub(r'[ً-ٰٟـ]','',t)
    for a,b in [('أ','ا'),('إ','ا'),('آ','ا'),('ى','ي'),('ة','ه'),('ؤ','و'),('ئ','ي'),('گ','ك'),('ڤ','ف'),('پ','ب')]: t=t.replace(a,b)
    return re.sub(r'[^ء-ي]','',t)
lines=[l.strip() for l in open(D+"script.txt").read().split('\n') if l.strip()]
dur=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",D+"voice.wav"],capture_output=True,text=True).stdout)
raw=subprocess.run(["ffmpeg","-v","error","-i",D+"voice.wav","-f","f32le","-ac","1","-ar","16000","-"],capture_output=True).stdout
a=np.frombuffer(raw,np.float32)
m=WhisperModel("small",compute_type="int8")
segs,_=m.transcribe(a,language="ar",word_timestamps=True,beam_size=5,condition_on_previous_text=False)
W=[]
for s in segs: W+=[(w.start,w.end,w.word) for w in s.words]
json.dump(W,open(D+"words.json","w"),ensure_ascii=False)
# whisper char stream with times
wc="";wt=[]
for s,e,w in W:
    n=norm(w)
    for i,c in enumerate(n): wc+=c; wt.append(s+(e-s)*i/max(1,len(n)))
sc="";lstart=[]
for l in lines: lstart.append(len(sc)); sc+=norm(l)
sm=difflib.SequenceMatcher(None,sc,wc,autojunk=False)
mp={}
for bl in sm.get_matching_blocks():
    for k in range(bl.size): mp[bl.a+k]=wt[bl.b+k]
# silences
o=subprocess.run(["ffmpeg","-i",D+"voice.wav","-af","silencedetect=noise=-35dB:d=0.15","-f","null","-"],capture_output=True,text=True).stderr
ss=[float(x) for x in re.findall(r"silence_start: ([\d.]+)",o)]; se=[float(x) for x in re.findall(r"silence_end: ([\d.]+)",o)]
gaps=list(zip(ss,se))
B=[0.0]
for i in range(1,len(lines)):
    p=lstart[i]; t=None
    for k in range(p,min(p+6,len(sc))):
        if k in mp: t=mp[k]-(k-p)*0.07; break
    if t is None: t=dur*p/len(sc)
    # snap to nearest gap end (sentence start right after a pause)
    c=[(abs(e-t),(s0+e)/2,e) for s0,e in gaps if abs(e-t)<0.6]
    if c: t=min(c)[2]-0.05
    B.append(round(t,2))
B.append(round(dur,2))
out=[[B[i],B[i+1],lines[i]] for i in range(len(lines))]
json.dump(out,open(D+"lines.json","w"),ensure_ascii=False,indent=0)
print("dur",round(dur,2),"match",round(sm.ratio(),3))
for s,e,t in out: print(f"{s:6.2f}-{e:6.2f} ({e-s:4.2f}) {t[:60]}")
