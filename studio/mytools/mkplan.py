# mkplan.py REF -> reads shots.json: [[lineIdx, clip, start, flag, weight?], ...] in order; lines.json; writes plan.json
# each line's duration is split among its shots by weight; flag may include |slow (source used = dur/1.5)
import sys,json,subprocess
D=f"/home/claude/work/{sys.argv[1]}/"
L=json.load(open(D+"lines.json")); S=json.load(open(D+"shots.json"))
def cd(v): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",D+f"src/{v}.mp4"],capture_output=True,text=True).stdout)
CD={}
plan=[];used={};ok=True
tail=0.6  # extra after voice end
for li in range(len(L)):
    sh=[s for s in S if s[0]==li]
    if not sh: print("NO SHOT for line",li); ok=False; continue
    d=L[li][1]-L[li][0]+(tail if li==len(L)-1 else 0)
    wsum=sum((s[4] if len(s)>4 else 1) for s in sh)
    for s in sh:
        v,a,f=s[1],s[2],s[3]; w=(s[4] if len(s)>4 else 1)
        import re
        m=re.search(r'\|s([\d.]+)',f); fac=1.5 if 'slow' in f else (float(m.group(1)) if m else 1)
        dd=d*w/wsum; src=dd/fac
        b=round(a+src,2)
        if v not in CD: CD[v]=cd(v)
        if b>CD[v]-0.05: print(f"!! line{li} {v} {a}-{b} beyond clip {CD[v]:.2f}"); ok=False
        for (x,y,l2) in used.get(v,[]):
            if a<y-0.05 and b>x+0.05: print(f"!! overlap {v} {a}-{b} with {x}-{y} (line{l2})"); ok=False
        used.setdefault(v,[]).append((a,b,li))
        plan.append([v,a,b,f]); print(f"line{li:2d} {v:4s} {a:6.2f}-{b:6.2f} out={dd:4.2f} {f}")
json.dump(plan,open(D+"plan.json","w"),ensure_ascii=False)
print("OK" if ok else "PROBLEMS")
