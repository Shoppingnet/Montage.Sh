# usage: tighten.py in.wav out.wav [maxgap=0.28]  -> trims lead/tail silence, shortens pauses > maxgap to maxgap
import sys,wave,numpy as np
w=wave.open(sys.argv[1]); sr=w.getframerate(); a=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(np.float32)
mg=float(sys.argv[3]) if len(sys.argv)>3 else 0.28
hop=int(sr*0.01); n=len(a)//hop
e=np.array([np.sqrt(np.mean(a[i*hop:(i+1)*hop]**2))+1e-9 for i in range(n)])
db=20*np.log10(e/32768); sil=db<-40
voiced=np.where(~sil)[0]; s0=max(0,voiced[0]-3); s1=min(n,voiced[-1]+8)
keep=[];i=s0
while i<s1:
    if sil[i]:
        j=i
        while j<s1 and sil[j]: j+=1
        L=j-i; k=int(mg*100)
        if L>k: keep+=list(range(i,i+k//2))+list(range(j-(k-k//2),j))
        else: keep+=list(range(i,j))
        i=j
    else: keep.append(i); i+=1
out=np.concatenate([a[k*hop:(k+1)*hop] for k in keep]).astype(np.int16)
o=wave.open(sys.argv[2],'wb'); o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr); o.writeframes(out.tobytes())
print(f"{len(a)/sr:.2f} -> {len(out)/sr:.2f}")
