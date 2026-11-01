# nb.py in.png out.png "prompt" [model]  — Nano Banana image edit with the Gemini key (never printed)
import sys,json,base64,urllib.request
i,o,pr=sys.argv[1:4]; mdl=sys.argv[4] if len(sys.argv)>4 else 'gemini-3-pro-image'
key=open('/home/claude/.gk').read().strip()
body={"contents":[{"parts":[{"text":pr},{"inlineData":{"mimeType":"image/png","data":base64.b64encode(open(i,'rb').read()).decode()}}]}],
 "generationConfig":{"responseModalities":["IMAGE"],"imageConfig":{"aspectRatio":"9:16"}}}
req=urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key})
try: r=json.load(urllib.request.urlopen(req,timeout=300))
except urllib.error.HTTPError as e: print('HTTP',e.code,e.read().decode()[:300]); sys.exit(1)
for p in r["candidates"][0]["content"]["parts"]:
    if "inlineData" in p: open(o,'wb').write(base64.b64decode(p["inlineData"]["data"])); print('OK',o); break
else: print('no image',str(r)[:300])
