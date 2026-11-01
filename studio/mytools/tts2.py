# tts2.py REF take  -> one TTS take (t<take>.pcm/.wav/t<take>t.wav); .gk first, then .gk2; on 429 on both, sleep the reported retryDelay (no tight loop)
import json,base64,sys,urllib.request,urllib.error,re,time,os,subprocess
R,tk=sys.argv[1],sys.argv[2]; os.chdir(f'/home/claude/work/{R}')
text=open('script.txt').read().strip().replace('\n',' ')
body={"contents":[{"parts":[{"text":text}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":"Laomedeia"}}}}}
def call(k):
    if not os.path.exists('/home/claude/'+k): return None,10**6
    key=open('/home/claude/'+k).read().strip()
    req=urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key})
    try:
        r=json.load(urllib.request.urlopen(req,timeout=240)); return r,0
    except urllib.error.HTTPError as e:
        t=e.read().decode(errors='ignore')
        if e.code==429:
            m=re.search(r'retry in ([\dhms.]+)',t) ; d=0
            if m:
                s=m.group(1); h=re.search(r'(\d+)h',s); mi=re.search(r'(\d+)m(?!s)',s); se=re.search(r'([\d.]+)s',s)
                d=(int(h.group(1))*3600 if h else 0)+(int(mi.group(1))*60 if mi else 0)+(float(se.group(1)) if se else 0)
            return None,max(d,30)
        print('HTTP',e.code,file=sys.stderr); return None,60
while True:
    r,d1=call('.gk')
    if r is None:
        r,d2=call('.gk2')
    if r is None:
        r,d3=call('.gk3')
    else: d3=d2
    if r is not None: break
    w=min(d1,d2,d3)+5; print(f'429 all keys, sleeping {w:.0f}s',flush=True); time.sleep(w)
p=r["candidates"][0]["content"]["parts"][0]["inlineData"]
open(f't{tk}.pcm','wb').write(base64.b64decode(p["data"]))
subprocess.run(['cp',f't{tk}.pcm',f't{tk}.wav'])
subprocess.run(['python3','/home/claude/toolsB/tighten.py',f't{tk}.wav',f't{tk}t.wav','0.28'])
print('OK',R,tk,flush=True)
