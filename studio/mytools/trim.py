# trim.py in.wav out.wav [maxgap=0.30]  -> trims lead/tail silence, shortens pauses longer than maxgap
import sys,wave,numpy as np
w=wave.open(sys.argv[1]); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(np.float32); w.close()
mg=float(sys.argv[3]) if len(sys.argv)>3 else 0.30
fr=int(sr*0.01); n=len(x)//fr
e=np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2)) for i in range(n)])
th=10**(-38/20)*32768
sil=e<th
keep=np.ones(n,bool)
# lead/tail
nz=np.where(~sil)[0]; a,b=max(0,nz[0]-5),min(n,nz[-1]+8)
keep[:a]=False; keep[b:]=False
i=a
while i<b:
    if sil[i]:
        j=i
        while j<b and sil[j]: j+=1
        L=j-i; m=int(mg*100)
        if L>m:
            h=m//2; keep[i+h:j-(m-h)]=False
        i=j
    else: i+=1
y=np.concatenate([x[k*fr:(k+1)*fr] for k in range(n) if keep[k]]).astype(np.int16)
o=wave.open(sys.argv[2],'wb'); o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr); o.writeframes(y.tobytes()); o.close()
print(f"{len(x)/sr:.2f} -> {len(y)/sr:.2f}")
