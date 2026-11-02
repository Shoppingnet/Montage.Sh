# nb.py in.png out.png "prompt" [model]  — Nano Banana image edit with the Gemini key (never printed)
import sys,json,base64,urllib.request
i,o,pr=sys.argv[1:4]; mdl=sys.argv[4] if len(sys.argv)>4 else 'gemini-3.1-flash-image'
body={"contents":[{"parts":[{"text":pr},{"inlineData":{"mimeType":"image/png","data":base64.b64encode(open(i,'rb').read()).decode()}}]}],
 "generationConfig":{"responseModalities":["IMAGE"],"imageConfig":{"aspectRatio":"9:16"}}}
import os
r=None
for k in ('.gk','.gk2','.gk3'):
    if not os.path.exists('/home/claude/'+k): continue
    key=open('/home/claude/'+k).read().strip()
    req=urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key})
    try: r=json.load(urllib.request.urlopen(req,timeout=300)); break
    except urllib.error.HTTPError as e:
        print('HTTP',e.code,'on',k,file=sys.stderr)
        if e.code in (402,429): continue
        print(e.read().decode()[:300]); sys.exit(1)
if r is None: print('all keys failed'); sys.exit(1)
for p in r["candidates"][0]["content"]["parts"]:
    if "inlineData" in p: open(o,'wb').write(base64.b64decode(p["inlineData"]["data"])); print('OK',o); break
else: print('no image',str(r)[:300])
