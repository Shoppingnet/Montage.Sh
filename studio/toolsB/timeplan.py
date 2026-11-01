# usage: timeplan.py <workdir>
# needs script.txt (one sentence per line; ending lines included), words.json, shots.json
# shots.json: list of [line_index, clip, start, flags]  (flags "" | "band:a-b" | "|slow"); several shots per line split the line time equally (or by optional 5th weight)
# writes plan.json; each shot runs from its line's start word to next line's start word
import sys,json,re,difflib,subprocess,os
W=sys.argv[1]; os.chdir(W)
def norm(t):
    t=re.sub(r'[ً-ٰٟـ]','',t)
    for a,b in [('أ','ا'),('إ','ا'),('آ','ا'),('ى','ي'),('ة','ه'),('ؤ','و'),('ئ','ي'),('ڤ','ف'),('گ','ك'),('پ','ب')]: t=t.replace(a,b)
    return re.sub(r'[^ء-ي]','',t)
lines=[l for l in open('script.txt').read().split('\n') if l.strip()]
words=json.load(open('words.json'))
S="";starts=[]
for l in lines: starts.append(len(S)); S+=norm(l)
H="";wpos=[]
for a,b,w in words:
    wpos.append(len(H)); H+=norm(w)
sm=difflib.SequenceMatcher(None,S,H,autojunk=False)
m={}
for blk in sm.get_matching_blocks():
    for k in range(blk.size): m[blk.a+k]=blk.b+k
def h2word(hp):
    k=0
    for i,p in enumerate(wpos):
        if p<=hp: k=i
    return k
dur=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0","voice.wav"],capture_output=True,text=True).stdout)
B=[0.0]
for i in range(1,len(lines)):
    sp=starts[i]
    cs=[c for c in range(sp,min(sp+10,len(S))) if c in m]
    if not cs: print("WARN no align line",i); cs=[sp]; m[sp]=int(sp*len(H)/len(S))
    k=h2word(max(0,m[cs[0]]-(cs[0]-sp)))
    t=words[k][0]; pe=words[k-1][1] if k>0 else 0
    B.append(round((t+pe)/2 if t-pe<0.6 else t-0.1,2))
T=dur+0.4+0.6
B.append(T)
for i,b in enumerate(B[:-1]):
    print(f"L{i} {b:6.2f}-{B[i+1]:6.2f} ({B[i+1]-b:4.1f}s) {lines[i][:70]}")
shots=json.load(open('shots.json'))
P=[];used={}
cd={}
def cdur(c):
    if c not in cd: cd[c]=float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f"src/{c}.mp4"],capture_output=True,text=True).stdout)
    return cd[c]
for i in range(len(lines)):
    L=[s for s in shots if s[0]==i]
    if not L: print("WARN no shot for line",i); continue
    tot=B[i+1]-B[i]; ws=[s[4] if len(s)>4 else 1 for s in L]
    for s,w in zip(L,ws):
        d=tot*w/sum(ws); f=s[3]; mm=re.search(r'\|sl([0-9.]+)',f); k=float(mm.group(1)) if mm else (1.5 if 'slow' in f else 1)
        a=s[2]; b=round(a+d/k,2)
        if b>cdur(s[1])-0.03: print(f"WARN L{i} {s[1]} {a}-{b} beyond clip end {cdur(s[1]):.2f}")
        for (aa,bb) in used.get(s[1],[]):
            if a<bb-0.05 and b>aa+0.05: print(f"WARN repeat L{i} {s[1]} {a}-{b} overlaps {aa}-{bb}")
        used.setdefault(s[1],[]).append((a,b))
        P.append([s[1],a,b,f])
json.dump(P,open('plan.json','w'),ensure_ascii=False)
print("voice",round(dur,2),"shots",len(P))
